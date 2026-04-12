"""Graph schema migration (0.4.0+).

0.4.0 introduced a path-based canonical ID scheme:

    {rel_path_slug}::{kind}::{local_slug}

Prior versions used ``{filestem}_{slug}`` which collided whenever two files
shared a basename across directories (``src/auth/utils.py::validate`` vs
``src/db/utils.py::validate``).

This module provides the **Option A** automatic migration path: it reads a
pre-0.4.0 ``graph.json``, derives the new canonical IDs from the existing
``source_file`` fields on each node, rewires edges through an old→new
mapping, and rewrites the file in place with ``schema_version: 2``.

If migration cannot proceed (malformed JSON, missing source_file on most
nodes, etc.), the function falls back to **Option E** — a clear instruction
that tells the user how to rebuild from scratch — and returns a sentinel so
the caller can trigger a full rebuild.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


CURRENT_SCHEMA_VERSION = 2


def _looks_canonical(node_id: str) -> bool:
    """True if a node ID is already in 0.4.0+ canonical format.

    The canonical format is ``{rel_path_slug}::{kind}::{local_slug}`` — we
    detect it by the presence of at least two ``::`` separators, which no
    pre-0.4.0 ID can possibly contain (``_sanitize_id`` collapses colons
    to underscores, so legacy IDs are always a single flat slug).
    """
    return isinstance(node_id, str) and node_id.count("::") >= 2


def migrate_graph_if_needed(
    graph_path: Path, index_root: Path | None = None,
) -> dict[str, Any]:
    """Migrate a pre-0.4.0 graph.json in place.

    Args:
        graph_path: Path to ``mindvault-out/graph.json``.
        index_root: Project root used to compute canonical path slugs. When
            omitted, the migration falls back to the file's own path parts,
            which produces longer slugs (``users__me__proj__notes__plan_md``)
            that still collision-safe but don't match what a fresh compile
            in ``source_dir`` would produce. Pass ``source_dir`` whenever
            possible.

    Returns:
        Dict with keys:
            migrated (bool): True if the file was rewritten.
            status (str): "already_current" | "migrated" | "missing" |
                          "needs_rebuild".
            dropped_placeholders (int): Number of placeholder nodes removed.
            node_count (int): Total nodes after migration.
    """
    if not graph_path.exists():
        return {
            "migrated": False,
            "status": "missing",
            "dropped_placeholders": 0,
            "node_count": 0,
        }

    try:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        _print_rebuild_instructions(graph_path, reason=f"graph.json parse error: {e}")
        return {
            "migrated": False,
            "status": "needs_rebuild",
            "dropped_placeholders": 0,
            "node_count": 0,
        }

    if data.get("schema_version", 1) >= CURRENT_SCHEMA_VERSION:
        return {
            "migrated": False,
            "status": "already_current",
            "dropped_placeholders": 0,
            "node_count": len(data.get("nodes", [])),
        }

    # Deferred import: extract.py is the single source of truth for the ID
    # scheme, migration reuses the exact same helpers.
    from mindvault.extract import _make_canonical_id, _make_ref_id

    raw_nodes = data.get("nodes", [])
    raw_links = data.get("links", []) or data.get("edges", [])

    # Sanity check — Option E fallback trigger. If the overwhelming majority
    # of nodes lack source_file, we can't derive canonical IDs and we tell
    # the user to rebuild from scratch rather than silently corrupting.
    missing_source = sum(
        1 for n in raw_nodes
        if not n.get("source_file") and n.get("file_type") != "placeholder"
    )
    non_placeholder = sum(
        1 for n in raw_nodes if n.get("file_type") != "placeholder"
    )
    if non_placeholder > 0 and missing_source / non_placeholder > 0.5:
        _print_rebuild_instructions(
            graph_path,
            reason=f"{missing_source}/{non_placeholder} nodes missing source_file",
        )
        return {
            "migrated": False,
            "status": "needs_rebuild",
            "dropped_placeholders": 0,
            "node_count": len(raw_nodes),
        }

    id_map: dict[str, str] = {}
    new_nodes: list[dict] = []
    dropped_placeholders = 0

    for node in raw_nodes:
        old_id = node.get("id", "")
        if not old_id:
            continue

        source_file = node.get("source_file") or ""
        label = node.get("label", "") or ""
        file_type = node.get("file_type", "") or ""
        source_location = node.get("source_location") or ""

        # Canonical passthrough — if the ID is already in 0.4.0+ format,
        # keep it as-is. This guards against the 0.4.0 export_json bug that
        # wrote canonical-content graphs without the `schema_version` stamp,
        # which migration would then mis-classify back to "entity" kind.
        if _looks_canonical(old_id):
            if file_type == "placeholder":
                dropped_placeholders += 1
                id_map[old_id] = _make_ref_id(label or old_id)
                continue
            id_map[old_id] = old_id
            # Backfill entity_type if missing (parseable from the ID's kind slot)
            if "entity_type" not in node:
                parts = old_id.split("::")
                if len(parts) >= 2 and parts[1]:
                    node["entity_type"] = parts[1]
            new_nodes.append(node)
            continue

        # Placeholder nodes (dangling refs) collapse to unresolved refs.
        # Drop them here — build_graph will recreate them from edge endpoints
        # the next time the graph is rebuilt.
        if file_type == "placeholder" or not source_file:
            id_map[old_id] = _make_ref_id(label or old_id)
            dropped_placeholders += 1
            continue

        kind = _infer_kind_v1(old_id, label, file_type, source_location)
        # file-level synthetic nodes have an empty local slug in the fresh
        # canonical scheme (label lives in the `label` field, not the ID).
        # Pass "" so migrated IDs match what a fresh compile produces.
        local_name = "" if kind == "file" else label
        new_id = _make_canonical_id(source_file, kind, local_name, index_root)
        id_map[old_id] = new_id
        node["id"] = new_id
        node.setdefault("entity_type", kind)
        new_nodes.append(node)

    # Rewire edges through the old→new map. Unknown IDs fall back to
    # unresolved ref format.
    new_links: list[dict] = []
    for link in raw_links:
        src = link.get("source", "")
        tgt = link.get("target", "")
        link["source"] = id_map.get(src, _make_ref_id(src) if src else src)
        link["target"] = id_map.get(tgt, _make_ref_id(tgt) if tgt else tgt)
        new_links.append(link)

    data["nodes"] = new_nodes
    # NetworkX JSON uses "links"; preserve whichever key was there.
    if "edges" in data and "links" not in data:
        data["edges"] = new_links
    else:
        data["links"] = new_links
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    migration_info = data.setdefault("migration_info", {})
    migration_info["migrated_from_v1"] = True
    migration_info["dropped_placeholder_nodes"] = dropped_placeholders

    graph_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"MindVault: migrated graph.json to schema v{CURRENT_SCHEMA_VERSION} "
        f"({len(new_nodes)} nodes, {dropped_placeholders} placeholders dropped)",
        file=sys.stderr,
    )

    return {
        "migrated": True,
        "status": "migrated",
        "dropped_placeholders": dropped_placeholders,
        "node_count": len(new_nodes),
    }


def _infer_kind_v1(
    old_id: str, label: str, file_type: str, source_location: str,
) -> str:
    """Guess the canonical ``kind`` for a pre-0.4.0 node.

    Heuristics (in order):
      1. ID suffix ``_file``   or ``source_location == "file"`` → ``file``
      2. ID suffix ``_module`` → ``module``
      3. ID suffix ``_lang``   → ``block``
      4. ``file_type == placeholder`` → ``ref``
      5. ``source_location`` like ``L42``   → ``class`` (if label starts
         uppercase and has no underscore, else ``function``)
      6. ``source_location`` like ``line 42`` → ``header``
      7. ``file_type == document``           → ``concept`` (LLM semantic)
      8. fallback → ``entity``

    Class-vs-function detection is a guess based on PEP8 CapWords
    convention, not authoritative. Migrated IDs for code entities may
    therefore diverge slightly from a fresh compile. This is acceptable
    because the next incremental/full rebuild will converge.
    """
    if old_id.endswith("_file") or source_location == "file":
        return "file"
    if old_id.endswith("_module"):
        return "module"
    if old_id.endswith("_lang"):
        return "block"
    if file_type == "placeholder":
        return "ref"
    if source_location and source_location.startswith("L"):
        if label and label[:1].isupper() and "_" not in label:
            return "class"
        return "function"
    if source_location and source_location.startswith("line "):
        return "header"
    if file_type == "document":
        return "concept"
    return "entity"


def _print_rebuild_instructions(graph_path: Path, *, reason: str) -> None:
    """Option E fallback: tell the user how to rebuild from scratch.

    Writes to stderr so it doesn't contaminate stdout (which some callers
    parse as JSON). Backs up the old graph.json so users can recover it
    manually if needed.
    """
    backup_path = graph_path.with_suffix(".json.v1.bak")
    try:
        backup_path.write_bytes(graph_path.read_bytes())
        backup_note = f" (backed up to {backup_path.name})"
    except (OSError, IOError):
        backup_note = ""

    project_root = graph_path.parent.parent
    print(
        "\n"
        "MindVault: could not auto-migrate graph.json to the 0.4.0 schema.\n"
        f"  Reason: {reason}{backup_note}\n"
        "  Action: rebuild the graph from scratch.\n"
        f"    rm -rf {graph_path.parent}\n"
        f"    mindvault install  # from inside {project_root}\n",
        file=sys.stderr,
    )
