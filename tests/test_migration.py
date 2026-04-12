"""Unit tests for the 0.4.0 graph.json migration (Option A + E).

Locks:
  - pre-0.4.0 nodes get rewritten to canonical IDs using source_file
  - edges get rewired through the old→new mapping
  - placeholder/dangling nodes get dropped and replaced by ref IDs
  - second run is idempotent (already_current)
  - Option E fallback triggers when source_file is missing on >50% of nodes
  - migrated IDs match what a fresh ingest would produce
"""

from __future__ import annotations

import json
from pathlib import Path

from mindvault.migrate import (
    CURRENT_SCHEMA_VERSION,
    migrate_graph_if_needed,
    _infer_kind_v1,
    _looks_canonical,
)


def _write_v1_graph(path: Path, nodes: list[dict], links: list[dict]) -> None:
    path.write_text(json.dumps({"nodes": nodes, "links": links}, indent=2))


class TestInferKindV1:
    def test_file_suffix(self):
        assert _infer_kind_v1("plan_file", "Plan", "document", "file") == "file"

    def test_module_suffix(self):
        assert _infer_kind_v1("utils_module", "utils", "code", None) == "module"

    def test_lang_suffix(self):
        assert _infer_kind_v1("plan_python_lang", "python", "document", "line 10") == "block"

    def test_placeholder(self):
        assert _infer_kind_v1("missing", "missing", "placeholder", None) == "ref"

    def test_code_function_via_L_location(self):
        assert _infer_kind_v1("utils_validate", "validate", "code", "L12") == "function"

    def test_code_class_via_capwords_label(self):
        assert _infer_kind_v1("utils_UserService", "UserService", "code", "L42") == "class"

    def test_code_class_underscore_label_is_function(self):
        """CapWords heuristic: if label has underscore, treat as function."""
        assert _infer_kind_v1("utils_user_service", "user_service", "code", "L42") == "function"

    def test_text_header_via_line_location(self):
        assert _infer_kind_v1("plan_intro", "Intro", "document", "line 5") == "header"

    def test_document_default_concept(self):
        assert _infer_kind_v1("some_concept", "concept", "document", "") == "concept"

    def test_fallback_entity(self):
        assert _infer_kind_v1("unknown", "unknown", "", "") == "entity"


class TestMigrationRoundtrip:
    def test_happy_path_rewrites_all_nodes(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        out = proj / "mindvault-out"
        out.mkdir()
        gp = out / "graph.json"

        _write_v1_graph(gp, [
            {"id": "plan_file", "label": "Plan",
             "file_type": "document",
             "source_file": str(proj / "notes" / "plan.md"),
             "source_location": "file"},
            {"id": "plan_intro", "label": "Intro",
             "file_type": "document",
             "source_file": str(proj / "notes" / "plan.md"),
             "source_location": "line 5"},
            {"id": "utils_module", "label": "utils",
             "file_type": "code",
             "source_file": str(proj / "src" / "auth" / "utils.py"),
             "source_location": None},
            {"id": "utils_validate", "label": "validate",
             "file_type": "code",
             "source_file": str(proj / "src" / "auth" / "utils.py"),
             "source_location": "L12"},
        ], [
            {"source": "plan_file", "target": "plan_intro", "relation": "contains"},
            {"source": "utils_module", "target": "utils_validate", "relation": "contains"},
        ])

        result = migrate_graph_if_needed(gp, index_root=proj)
        assert result["migrated"] is True
        assert result["status"] == "migrated"
        assert result["node_count"] == 4

        migrated = json.loads(gp.read_text())
        assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION
        node_ids = {n["id"] for n in migrated["nodes"]}
        assert "notes__plan_md::file::" in node_ids
        assert "notes__plan_md::header::intro" in node_ids
        assert "src__auth__utils_py::module::utils" in node_ids
        assert "src__auth__utils_py::function::validate" in node_ids

    def test_edges_rewired_through_id_map(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        out = proj / "mindvault-out"
        out.mkdir()
        gp = out / "graph.json"

        _write_v1_graph(gp, [
            {"id": "plan_file", "label": "Plan",
             "file_type": "document",
             "source_file": str(proj / "plan.md"),
             "source_location": "file"},
            {"id": "plan_intro", "label": "Intro",
             "file_type": "document",
             "source_file": str(proj / "plan.md"),
             "source_location": "line 3"},
        ], [
            {"source": "plan_file", "target": "plan_intro", "relation": "contains"},
        ])

        migrate_graph_if_needed(gp, index_root=proj)
        migrated = json.loads(gp.read_text())

        assert len(migrated["links"]) == 1
        link = migrated["links"][0]
        assert link["source"] == "plan_md::file::"
        assert link["target"] == "plan_md::header::intro"

    def test_placeholder_nodes_dropped(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        out = proj / "mindvault-out"
        out.mkdir()
        gp = out / "graph.json"

        _write_v1_graph(gp, [
            {"id": "utils_module", "label": "utils",
             "file_type": "code",
             "source_file": str(proj / "utils.py"),
             "source_location": None},
            {"id": "missing_helper", "label": "missing_helper",
             "file_type": "placeholder",
             "source_file": "",
             "source_location": None},
        ], [
            {"source": "utils_module", "target": "missing_helper", "relation": "calls"},
        ])

        result = migrate_graph_if_needed(gp, index_root=proj)
        assert result["dropped_placeholders"] == 1

        migrated = json.loads(gp.read_text())
        assert len(migrated["nodes"]) == 1  # placeholder dropped
        # Edge still exists but target is now a ref
        assert len(migrated["links"]) == 1
        assert migrated["links"][0]["target"] == "__unresolved__::ref::missing_helper"

    def test_idempotent_second_run(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        out = proj / "mindvault-out"
        out.mkdir()
        gp = out / "graph.json"

        _write_v1_graph(gp, [
            {"id": "plan_file", "label": "Plan",
             "file_type": "document",
             "source_file": str(proj / "plan.md"),
             "source_location": "file"},
        ], [])

        migrate_graph_if_needed(gp, index_root=proj)
        result2 = migrate_graph_if_needed(gp, index_root=proj)
        assert result2["migrated"] is False
        assert result2["status"] == "already_current"

    def test_missing_file_returns_missing(self, tmp_path: Path):
        gp = tmp_path / "nonexistent.json"
        result = migrate_graph_if_needed(gp, index_root=tmp_path)
        assert result["status"] == "missing"
        assert result["migrated"] is False

    def test_already_current_skips(self, tmp_path: Path):
        gp = tmp_path / "graph.json"
        gp.write_text(json.dumps({
            "schema_version": CURRENT_SCHEMA_VERSION,
            "nodes": [{"id": "already__canonical::file::"}],
            "links": [],
        }))
        result = migrate_graph_if_needed(gp, index_root=tmp_path)
        assert result["status"] == "already_current"
        assert result["migrated"] is False


class TestMigrationFallbackOptionE:
    def test_missing_source_file_triggers_rebuild(self, tmp_path: Path, capsys):
        """When >50% of non-placeholder nodes lack source_file, fallback to E."""
        proj = tmp_path / "proj"
        proj.mkdir()
        out = proj / "mindvault-out"
        out.mkdir()
        gp = out / "graph.json"

        _write_v1_graph(gp, [
            {"id": "n1", "label": "n1", "file_type": "document", "source_file": "", "source_location": None},
            {"id": "n2", "label": "n2", "file_type": "document", "source_file": "", "source_location": None},
            {"id": "n3", "label": "n3", "file_type": "document",
             "source_file": str(proj / "a.md"), "source_location": None},
        ], [])

        result = migrate_graph_if_needed(gp, index_root=proj)
        assert result["status"] == "needs_rebuild"
        assert result["migrated"] is False
        captured = capsys.readouterr()
        assert "auto-migrate" in captured.err
        assert "mindvault install" in captured.err

    def test_malformed_json_triggers_rebuild(self, tmp_path: Path, capsys):
        gp = tmp_path / "graph.json"
        gp.write_text("not valid json {{{ ")
        result = migrate_graph_if_needed(gp, index_root=tmp_path)
        assert result["status"] == "needs_rebuild"
        captured = capsys.readouterr()
        assert "parse error" in captured.err

    def test_backup_written_on_rebuild_trigger(self, tmp_path: Path, capsys):
        gp = tmp_path / "graph.json"
        gp.write_text("malformed {{")
        migrate_graph_if_needed(gp, index_root=tmp_path)
        backup = gp.with_suffix(".json.v1.bak")
        assert backup.exists()
        assert backup.read_text() == "malformed {{"


class TestLooksCanonical:
    """0.4.1 regression: detect pre-migrated canonical IDs."""

    def test_detects_basic_canonical(self):
        assert _looks_canonical("src__auth__utils_py::function::validate") is True

    def test_detects_file_node_empty_local(self):
        assert _looks_canonical("notes__plan_md::file::") is True

    def test_detects_ref_id(self):
        assert _looks_canonical("__unresolved__::ref::foo") is True

    def test_detects_global_prefixed_canonical(self):
        """Global pipeline prefixes IDs with ``{project}/`` — still canonical."""
        assert _looks_canonical("base-mcp/index_js::module::index") is True

    def test_rejects_legacy_flat_id(self):
        assert _looks_canonical("plan_file") is False
        assert _looks_canonical("utils_validate") is False
        assert _looks_canonical("utils_module") is False

    def test_rejects_single_colon_pair(self):
        """A single ``::`` is not enough — need at least two (kind + local)."""
        assert _looks_canonical("foo::bar") is False

    def test_rejects_non_string(self):
        assert _looks_canonical(None) is False  # type: ignore
        assert _looks_canonical(123) is False  # type: ignore


class TestCanonicalPassthrough:
    """0.4.1 regression guard for the export_json schema_version bug.

    Before 0.4.1, export_json wrote graph.json without the `schema_version`
    field, which made migrate_graph_if_needed treat already-canonical graphs
    as v1 and mis-classify every node as `entity` kind. These tests lock the
    fix: canonical IDs pass through unchanged and get stamped with
    schema_version:2.
    """

    def test_canonical_graph_passthrough_stamps_schema(self, tmp_path: Path):
        """A graph that's already canonical (but missing schema_version)
        should get the stamp without touching any node IDs."""
        proj = tmp_path / "proj"
        proj.mkdir()
        out = proj / "mindvault-out"
        out.mkdir()
        gp = out / "graph.json"

        canonical_nodes = [
            {"id": "src__auth__utils_py::module::utils",
             "label": "utils", "file_type": "code",
             "source_file": str(proj / "src" / "auth" / "utils.py"),
             "source_location": None,
             "entity_type": "module"},
            {"id": "src__auth__utils_py::function::validate",
             "label": "validate", "file_type": "code",
             "source_file": str(proj / "src" / "auth" / "utils.py"),
             "source_location": "L12",
             "entity_type": "function"},
            {"id": "notes__plan_md::file::",
             "label": "Plan", "file_type": "document",
             "source_file": str(proj / "notes" / "plan.md"),
             "source_location": "file",
             "entity_type": "file"},
            {"id": "notes__plan_md::header::intro",
             "label": "Intro", "file_type": "document",
             "source_file": str(proj / "notes" / "plan.md"),
             "source_location": "line 5",
             "entity_type": "header"},
        ]
        canonical_links = [
            {"source": "src__auth__utils_py::module::utils",
             "target": "src__auth__utils_py::function::validate",
             "relation": "contains"},
            {"source": "notes__plan_md::file::",
             "target": "notes__plan_md::header::intro",
             "relation": "contains"},
        ]
        _write_v1_graph(gp, canonical_nodes, canonical_links)

        result = migrate_graph_if_needed(gp, index_root=proj)
        assert result["migrated"] is True
        assert result["node_count"] == 4

        migrated = json.loads(gp.read_text())
        assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION

        # Critical: node IDs must be unchanged — no re-derivation
        migrated_ids = {n["id"] for n in migrated["nodes"]}
        assert migrated_ids == {n["id"] for n in canonical_nodes}

        # Entity types must be unchanged (NOT collapsed to "entity")
        kinds = {n["id"]: n["entity_type"] for n in migrated["nodes"]}
        assert kinds["src__auth__utils_py::module::utils"] == "module"
        assert kinds["src__auth__utils_py::function::validate"] == "function"
        assert kinds["notes__plan_md::file::"] == "file"
        assert kinds["notes__plan_md::header::intro"] == "header"

        # Edges must still match (no rewiring of canonical IDs)
        assert len(migrated["links"]) == 2
        sources = {link["source"] for link in migrated["links"]}
        assert sources == {
            "src__auth__utils_py::module::utils",
            "notes__plan_md::file::",
        }

    def test_canonical_graph_backfills_missing_entity_type(self, tmp_path: Path):
        """A pre-0.4.0 canonical graph might not have entity_type (old bug path)
        — migration should parse it from the ID's kind slot."""
        proj = tmp_path / "proj"
        proj.mkdir()
        gp = proj / "graph.json"
        _write_v1_graph(gp, [
            # Canonical ID but NO entity_type field
            {"id": "src__a_py::function::foo", "label": "foo",
             "file_type": "code",
             "source_file": str(proj / "src" / "a.py"),
             "source_location": "L10"},
        ], [])

        migrate_graph_if_needed(gp, index_root=proj)
        migrated = json.loads(gp.read_text())
        node = migrated["nodes"][0]
        assert node["id"] == "src__a_py::function::foo"
        assert node["entity_type"] == "function"  # backfilled from ID

    def test_mixed_legacy_and_canonical_graph(self, tmp_path: Path):
        """Edge case: half legacy, half canonical in the same file.
        Legacy nodes get migrated; canonical ones pass through."""
        proj = tmp_path / "proj"
        proj.mkdir()
        gp = proj / "graph.json"
        _write_v1_graph(gp, [
            # Legacy
            {"id": "utils_validate", "label": "validate", "file_type": "code",
             "source_file": str(proj / "src" / "utils.py"),
             "source_location": "L5"},
            # Already canonical
            {"id": "notes__plan_md::header::intro", "label": "Intro",
             "file_type": "document",
             "source_file": str(proj / "notes" / "plan.md"),
             "source_location": "line 3",
             "entity_type": "header"},
        ], [])

        migrate_graph_if_needed(gp, index_root=proj)
        migrated = json.loads(gp.read_text())
        ids = {n["id"] for n in migrated["nodes"]}
        # Legacy got rewritten
        assert "src__utils_py::function::validate" in ids
        # Canonical survived
        assert "notes__plan_md::header::intro" in ids
        # No "entity"-collapsed version
        assert "notes__plan_md::entity::intro" not in ids


class TestExportStampsSchemaVersion:
    """0.4.1 regression: export_json must write schema_version:2.

    This is the underlying fix that avoids triggering the migration
    mis-classification in the first place.
    """

    def test_export_json_writes_schema_version(self, tmp_path: Path):
        import networkx as nx
        from mindvault.export import export_json

        G = nx.DiGraph()
        G.add_node("a::file::", label="A", source_file="/x/a.md")
        G.add_node("a::header::intro", label="Intro", source_file="/x/a.md")
        G.add_edge("a::file::", "a::header::intro", relation="contains")

        out = tmp_path / "graph.json"
        export_json(G, {0: ["a::file::", "a::header::intro"]}, out)

        data = json.loads(out.read_text())
        assert data.get("schema_version") == CURRENT_SCHEMA_VERSION
