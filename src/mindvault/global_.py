"""Global pipeline: discover projects -> per-project pipeline -> merge -> unified output."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from mindvault.discover import discover_projects


def run_global(root: Path, output_dir: Path = None, max_depth: int = 4) -> dict:
    """Discover projects under root, run pipeline on each, merge into unified graph/wiki/index.

    Args:
        root: Root directory to scan for projects.
        output_dir: Global output directory (default: ~/.mindvault/).
        max_depth: Max BFS depth for project discovery.

    Returns:
        Dict with stats: projects, total_nodes, total_edges, cross_project_edges,
                         wiki_pages, index_docs.
    """
    from mindvault.pipeline import run as pipeline_run
    from mindvault.build import build_graph
    from mindvault.cluster import cluster, score_cohesion
    from mindvault.wiki import generate_wiki, _community_label
    from mindvault.export import export_json, export_html
    from mindvault.index import index_markdown

    root = Path(root).resolve()
    if output_dir is None:
        output_dir = Path.home() / ".mindvault"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Discover projects
    projects = discover_projects(root, max_depth)
    if not projects:
        return {
            "projects": 0, "total_nodes": 0, "total_edges": 0,
            "cross_project_edges": 0, "wiki_pages": 0, "index_docs": 0,
        }

    # 2. Run pipeline on each project
    project_results = []
    all_nodes = []
    all_edges = []

    for proj in projects:
        proj_output = output_dir / proj["name"]
        try:
            result = pipeline_run(proj["path"], proj_output)
        except Exception as e:
            result = {"nodes": 0, "edges": 0, "communities": 0, "wiki_pages": 0}

        # Load project graph
        graph_path = proj_output / "graph.json"
        proj_nodes = 0
        proj_edges = 0
        if graph_path.exists():
            try:
                gdata = json.loads(graph_path.read_text(encoding="utf-8"))
                raw_nodes = gdata.get("nodes", [])
                raw_links = gdata.get("links", [])

                # Prefix node IDs with project name
                for node in raw_nodes:
                    node["id"] = f"{proj['name']}/{node['id']}"
                    node["project"] = proj["name"]
                    all_nodes.append(node)

                # Prefix edge endpoints
                for link in raw_links:
                    link["source"] = f"{proj['name']}/{link['source']}"
                    link["target"] = f"{proj['name']}/{link['target']}"
                    link["project"] = proj["name"]
                    all_edges.append(link)

                proj_nodes = len(raw_nodes)
                proj_edges = len(raw_links)
            except (json.JSONDecodeError, OSError):
                pass

        project_results.append({
            "name": proj["name"],
            "path": str(proj["path"]),
            "type": proj["type"],
            "nodes": proj_nodes,
            "edges": proj_edges,
        })

    # 3. Add cross-project edges (shares_name_with)
    # Group nodes by their base name (without project prefix)
    from collections import defaultdict
    name_to_nodes: dict[str, list[str]] = defaultdict(list)
    for node in all_nodes:
        # Extract base name: project/file_entity -> entity part
        full_id = node["id"]
        base = full_id.split("/", 1)[1] if "/" in full_id else full_id
        # Use the node label or the last part of the ID
        label = node.get("label", base)
        name_to_nodes[label].append(full_id)

    # Filter out generic/noisy labels that create meaningless cross-project edges
    GENERIC_LABELS = {
        "Props", "props", "default", "index", "main", "App", "app",
        "config", "Config", "utils", "helpers", "types", "constants",
        "styles", "theme", "Layout", "layout", "Root", "root",
        "Home", "home", "Header", "header", "Footer", "footer",
        "Button", "button", "Modal", "modal", "Error", "error",
        "Loading", "loading", "Container", "container",
        "module", "Module", "init", "__init__",
    }

    cross_edges = 0
    for label, node_ids in name_to_nodes.items():
        if len(node_ids) < 2:
            continue
        # Skip generic labels
        if label in GENERIC_LABELS or len(label) <= 3:
            continue
        # Get unique projects
        projects_set = set()
        for nid in node_ids:
            proj_name = nid.split("/", 1)[0]
            projects_set.add(proj_name)
        if len(projects_set) < 2:
            continue
        # Add edges between nodes from different projects
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                p1 = node_ids[i].split("/", 1)[0]
                p2 = node_ids[j].split("/", 1)[0]
                if p1 != p2:
                    all_edges.append({
                        "source": node_ids[i],
                        "target": node_ids[j],
                        "relation": "shares_name_with",
                        "confidence": "INFERRED",
                        "confidence_score": 0.6,
                        "weight": 0.5,
                    })
                    cross_edges += 1

    # 4. Build unified graph
    merged = {"nodes": all_nodes, "edges": all_edges}
    G = build_graph(merged)

    # 5. Cluster + wiki + export
    communities = cluster(G)
    cohesion = score_cohesion(G, communities)
    labels = {}
    for cid, members in communities.items():
        labels[cid] = _community_label(G, members)

    wiki_pages = generate_wiki(G, communities, labels, output_dir, cohesion=cohesion)
    export_json(G, communities, output_dir / "graph.json")
    export_html(G, communities, labels, output_dir / "graph.html")

    # 6. Build unified search index
    wiki_dir = output_dir / "wiki"
    index_path = output_dir / "search_index.json"
    index_docs = 0
    if wiki_dir.exists():
        index_docs = index_markdown(wiki_dir, index_path)

    # 6b. Also index Claude Code memory files if they exist
    from mindvault.pipeline import _index_source_docs
    memory_patterns = [
        Path.home() / ".claude" / "projects",
    ]
    for mem_root in memory_patterns:
        if mem_root.exists():
            for memory_dir in mem_root.rglob("memory"):
                if memory_dir.is_dir():
                    md_files = [str(f.relative_to(memory_dir)) for f in memory_dir.glob("*.md")]
                    if md_files:
                        _index_source_docs(memory_dir, md_files, index_path)
                        index_docs += len(md_files)

    # 7. Save projects manifest
    manifest = {
        "root": str(root),
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "projects": project_results,
    }
    (output_dir / "projects.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "projects": len(projects),
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "cross_project_edges": cross_edges,
        "wiki_pages": wiki_pages,
        "index_docs": index_docs,
    }


def run_global_incremental(root: Path, output_dir: Path = None) -> dict:
    """Incremental global update: reload projects.json, run incremental on each.

    Args:
        root: Root directory.
        output_dir: Global output directory (default: ~/.mindvault/).

    Returns:
        Dict with update stats.
    """
    from mindvault.pipeline import run_incremental

    root = Path(root).resolve()
    if output_dir is None:
        output_dir = Path.home() / ".mindvault"
    output_dir = Path(output_dir)

    manifest_path = output_dir / "projects.json"
    if not manifest_path.exists():
        # No prior build — run full
        return run_global(root, output_dir)

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return run_global(root, output_dir)

    # Re-discover to find new/removed projects
    current_projects = discover_projects(root)
    current_names = {p["name"] for p in current_projects}
    known_names = {p["name"] for p in manifest.get("projects", [])}

    new_projects = current_names - known_names
    removed_projects = known_names - current_names

    # Run incremental on existing projects
    updated = 0
    for proj in current_projects:
        proj_output = output_dir / proj["name"]
        if proj["name"] in new_projects:
            # New project — full pipeline
            from mindvault.pipeline import run as pipeline_run
            try:
                pipeline_run(proj["path"], proj_output)
                updated += 1
            except Exception:
                pass
        else:
            # Existing — incremental
            try:
                result = run_incremental(proj["path"], proj_output)
                if result.get("changed", 0) > 0:
                    updated += 1
            except Exception:
                pass

    # Clean up removed projects
    import shutil
    for name in removed_projects:
        removed_dir = output_dir / name
        if removed_dir.exists():
            shutil.rmtree(removed_dir)

    # Update manifest
    project_results = []
    for proj in current_projects:
        graph_path = output_dir / proj["name"] / "graph.json"
        nodes = 0
        if graph_path.exists():
            try:
                gdata = json.loads(graph_path.read_text(encoding="utf-8"))
                nodes = len(gdata.get("nodes", []))
            except (json.JSONDecodeError, OSError):
                pass
        project_results.append({
            "name": proj["name"],
            "path": str(proj["path"]),
            "type": proj["type"],
            "nodes": nodes,
        })

    manifest = {
        "root": str(root),
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "projects": project_results,
    }
    (output_dir / "projects.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "updated": updated,
        "new_projects": len(new_projects),
        "removed_projects": len(removed_projects),
        "total_projects": len(current_projects),
    }
