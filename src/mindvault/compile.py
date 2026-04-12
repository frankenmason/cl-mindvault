"""Graph-to-wiki compilation (incremental)."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from mindvault.detect import detect
from mindvault.extract import extract_ast, extract_document_structure, extract_semantic
from mindvault.build import build_graph
from mindvault.cluster import cluster, score_cohesion
from mindvault.analyze import god_nodes, surprising_connections, suggest_questions
from mindvault.wiki import generate_wiki, update_wiki, _community_label
from mindvault.export import export_json, export_html
from mindvault.report import generate_report


def _merge_extractions(*results: dict) -> dict:
    """Merge variable number of extraction results.

    Nodes are deduplicated by ID (first occurrence wins).
    Merge order determines priority: earlier results take precedence.
    """
    seen_ids: set[str] = set()
    merged_nodes: list[dict] = []
    merged_edges: list[dict] = []
    total_input = 0
    total_output = 0

    for result in results:
        for node in result.get("nodes", []):
            nid = node.get("id", "")
            if nid not in seen_ids:
                seen_ids.add(nid)
                merged_nodes.append(node)
        merged_edges.extend(result.get("edges", []))
        total_input += result.get("input_tokens", 0)
        total_output += result.get("output_tokens", 0)

    return {
        "nodes": merged_nodes,
        "edges": merged_edges,
        "input_tokens": total_input,
        "output_tokens": total_output,
    }


def _find_changed_nodes(old_graph_path: Path, new_G: nx.DiGraph) -> list[str]:
    """Compare old graph.json with new graph to find truly changed nodes.

    Change criteria: node added, node deleted, node's edges changed,
    or node's source_file changed.

    Args:
        old_graph_path: Path to existing graph.json.
        new_G: Newly built NetworkX DiGraph.

    Returns:
        List of changed node IDs. First build returns all nodes.
    """
    if not old_graph_path.exists():
        return list(new_G.nodes())  # First build = all nodes

    try:
        old_data = json.loads(old_graph_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return list(new_G.nodes())

    old_nodes = {n["id"]: n for n in old_data.get("nodes", [])}
    old_edges: dict[str, set[str]] = {}
    for link in old_data.get("links", []):
        src = link.get("source", "")
        old_edges.setdefault(src, set()).add(link.get("target", ""))

    changed: list[str] = []
    new_node_ids = set(new_G.nodes())
    old_node_ids = set(old_nodes.keys())

    # Added nodes
    changed.extend(new_node_ids - old_node_ids)

    # Deleted nodes (not in new graph, but neighbors of deleted nodes may be affected)
    # We don't add deleted nodes themselves (they're gone), but this info
    # is used by update_wiki to know which communities need refresh.
    deleted = old_node_ids - new_node_ids

    # Nodes present in both — check for edge or source_file changes
    for node_id in new_node_ids & old_node_ids:
        # Edge change
        new_neighbors = set(new_G.successors(node_id))
        old_neighbors = old_edges.get(node_id, set())
        if new_neighbors != old_neighbors:
            changed.append(node_id)
            continue
        # Source file change
        new_sf = new_G.nodes[node_id].get("source_file", "")
        old_sf = old_nodes[node_id].get("source_file", "")
        if new_sf != old_sf:
            changed.append(node_id)

    # For deleted nodes: find their old neighbors that still exist
    # (those communities need refreshing too)
    for del_id in deleted:
        for neighbor in old_edges.get(del_id, set()):
            if neighbor in new_node_ids:
                changed.append(neighbor)

    return list(set(changed))


def _generate_labels(G, communities: dict[int, list[str]]) -> dict[int, str]:
    """Generate human-readable labels for each community."""
    labels: dict[int, str] = {}
    for cid, members in communities.items():
        labels[cid] = _community_label(G, members)
    return labels


def _finalize_and_export(
    G: nx.DiGraph,
    source_dir: Path,
    output_dir: Path,
    detection: dict,
    *,
    incremental: bool = True,
    write_report: bool = True,
) -> dict:
    """Shared finalization tail: cluster → analyze → wiki → export → report.

    Called by both ``compile()`` (full build) and ``run_incremental()`` (merged
    partial build). Centralizes the logic that used to be duplicated across
    both entry points (Codex finding #9).

    Args:
        G: NetworkX DiGraph built from an extraction result.
        source_dir: Project root (for report metadata).
        output_dir: MindVault output directory.
        detection: Result of ``detect(source_dir)``; used for report stats.
        incremental: If True and a wiki already exists, update only changed
            nodes; otherwise regenerate the full wiki.
        write_report: If True, write GRAPH_REPORT.md with gods/surprises stats.
            Off for lightweight incremental updates that don't need the report.

    Returns:
        Dict with stats: {nodes, edges, communities, wiki_pages, cohesion, labels}.
    """
    # Cluster communities
    communities = cluster(G)
    cohesion = score_cohesion(G, communities)

    # Generate labels
    labels = _generate_labels(G, communities)

    # Wiki: incremental if existing wiki is present, full otherwise
    wiki_dir = output_dir / "wiki"
    concepts_path = wiki_dir / "_concepts.json"
    graph_path = output_dir / "graph.json"
    if incremental and wiki_dir.exists() and concepts_path.exists():
        # True incremental: diff old graph.json against new graph
        changed_nodes = _find_changed_nodes(graph_path, G)
        wiki_pages = update_wiki(G, changed_nodes, output_dir, cohesion=cohesion)
    else:
        wiki_pages = generate_wiki(G, communities, labels, output_dir, cohesion=cohesion)

    # Export JSON (after wiki so next build can diff against this)
    export_json(G, communities, output_dir / "graph.json")

    # Export HTML
    export_html(G, communities, labels, output_dir / "graph.html")

    # Analysis + report (optional — expensive on large graphs)
    if write_report:
        gods = god_nodes(G)
        surprises = surprising_connections(G, communities)
        questions = suggest_questions(G, communities, labels)
        report_md = generate_report(
            G, communities, cohesion, labels, gods, surprises,
            detection, str(source_dir), questions,
        )
        (output_dir / "GRAPH_REPORT.md").write_text(report_md, encoding="utf-8")

    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "communities": len(communities),
        "wiki_pages": wiki_pages,
        "cohesion": cohesion,
        "labels": labels,
    }


def compile(source_dir: Path, output_dir: Path, incremental: bool = True) -> dict:
    """Full pipeline: detect → extract → build → cluster → wiki → export → report.

    Args:
        source_dir: Root directory of the project to compile.
        output_dir: Directory for MindVault output.
        incremental: If True and an existing wiki is present, perform
            incremental wiki updates (changed-nodes only). Extraction itself
            is always full — use ``pipeline.run_incremental`` for dirty-only
            extraction.

    Returns:
        Dict with stats: {nodes, edges, communities, wiki_pages, total_words}.
    """
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Detect files
    detection = detect(source_dir)
    code_files = [source_dir / f for f in detection["files"].get("code", [])]
    doc_files = [source_dir / f for f in detection["files"].get("document", [])]
    data_files = [source_dir / f for f in detection["files"].get("data", [])]

    # 2. Extract AST + Document Structure + Semantic.
    # source_dir is passed as the canonical index_root so all node IDs are
    # derived from project-relative paths (collision-safe across same-stem
    # files in different directories).
    ast_result = extract_ast(code_files, index_root=source_dir)
    doc_result = extract_document_structure(doc_files + data_files, index_root=source_dir)
    sem_result = extract_semantic(doc_files, output_dir, index_root=source_dir)
    extraction = _merge_extractions(ast_result, doc_result, sem_result)

    # 3. Build graph
    G = build_graph(extraction)

    # 4. Finalize: cluster → wiki → export → report (shared with run_incremental)
    stats = _finalize_and_export(
        G, source_dir, output_dir, detection,
        incremental=incremental, write_report=True,
    )

    return {
        "nodes": stats["nodes"],
        "edges": stats["edges"],
        "communities": stats["communities"],
        "wiki_pages": stats["wiki_pages"],
        "total_words": detection.get("total_words", 0),
    }
