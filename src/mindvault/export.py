"""Export -- graph.json, graph.html, wiki/ output."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
from networkx.readwrite.json_graph import node_link_data

from mindvault.wiki import generate_wiki


# Community color palette (10 distinct colors)
_COLORS = [
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8", "#f58231",
    "#911eb4", "#42d4f4", "#f032e6", "#bfef45", "#fabed4",
]


def export_json(
    G: nx.DiGraph,
    communities: dict[int, list[str]],
    output_path: Path,
) -> None:
    """Export graph as JSON with community data.

    Args:
        G: NetworkX DiGraph.
        communities: Dict mapping community_id to list of node_ids.
        output_path: Path to write graph.json.
    """
    from mindvault.migrate import CURRENT_SCHEMA_VERSION

    data = node_link_data(G, edges="links")
    data["communities"] = {str(k): v for k, v in communities.items()}
    # Stamp the schema version so migrate_graph_if_needed treats this file
    # as already-current on future incremental runs.
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def export_html(
    G: nx.DiGraph,
    communities: dict[int, list[str]],
    labels: dict[int, str],
    output_path: Path,
) -> None:
    """Export graph as interactive vis.js HTML visualization.

    Args:
        G: NetworkX DiGraph.
        communities: Dict mapping community_id to list of node_ids.
        labels: Dict mapping community_id to human-readable label.
        output_path: Path to write graph.html.
    """
    if G.number_of_nodes() > 5000:
        print(f"WARNING: Graph has {G.number_of_nodes()} nodes (>5000). Skipping HTML export.")
        return

    # Build node-to-community lookup
    node_to_comm: dict[str, int] = {}
    for cid, members in communities.items():
        for m in members:
            node_to_comm[m] = cid

    # Build vis.js nodes
    max_degree = max((G.degree(n) for n in G.nodes()), default=1)
    if max_degree == 0:
        max_degree = 1

    vis_nodes = []
    for nid in G.nodes():
        data = G.nodes[nid]
        lbl = data.get("label", nid)
        deg = G.degree(nid)
        cid = node_to_comm.get(nid, 0)
        color = _COLORS[cid % len(_COLORS)]
        size = 10 + (deg / max_degree) * 40
        vis_nodes.append({
            "id": nid,
            "label": lbl,
            "color": color,
            "size": round(size, 1),
            "community": cid,
            "title": f"{lbl} (degree: {deg}, community: {labels.get(cid, cid)})",
        })

    vis_edges = []
    for u, v, edata in G.edges(data=True):
        rel = edata.get("relation", "")
        vis_edges.append({
            "from": u,
            "to": v,
            "label": rel,
            "arrows": "to",
        })

    # Build community checkboxes data
    comm_list = []
    for cid in sorted(communities.keys()):
        lbl = labels.get(cid, f"Community {cid}")
        color = _COLORS[cid % len(_COLORS)]
        comm_list.append({"id": cid, "label": lbl, "color": color})

    nodes_json = json.dumps(vis_nodes, default=str)
    edges_json = json.dumps(vis_edges, default=str)
    comm_json = json.dumps(comm_list, default=str)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MindVault Knowledge Graph</title>
<script src="https://unpkg.com/vis-network/standalone/uml/vis-network.min.js"></script>
<style>
  body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, sans-serif; }}
  #controls {{ position: fixed; top: 10px; left: 10px; z-index: 10; background: white;
    padding: 12px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    max-height: 90vh; overflow-y: auto; }}
  #controls h3 {{ margin: 0 0 8px 0; font-size: 14px; }}
  #search {{ width: 200px; padding: 6px; margin-bottom: 8px; border: 1px solid #ccc;
    border-radius: 4px; font-size: 13px; }}
  .comm-filter {{ display: flex; align-items: center; gap: 6px; margin: 4px 0; font-size: 13px; }}
  .comm-dot {{ width: 12px; height: 12px; border-radius: 50%; display: inline-block; }}
  #graph {{ width: 100vw; height: 100vh; }}
</style>
</head>
<body>
<div id="controls">
  <h3>MindVault Graph</h3>
  <input type="text" id="search" placeholder="Search nodes..." />
  <div id="filters"></div>
</div>
<div id="graph"></div>
<script>
const allNodes = {nodes_json};
const allEdges = {edges_json};
const communities = {comm_json};

const nodes = new vis.DataSet(allNodes);
const edges = new vis.DataSet(allEdges);

const container = document.getElementById('graph');
const data = {{ nodes, edges }};
const options = {{
  physics: {{ stabilization: {{ iterations: 150 }}, barnesHut: {{ gravitationalConstant: -3000 }} }},
  edges: {{ font: {{ size: 10, color: '#888' }}, smooth: {{ type: 'continuous' }} }},
  nodes: {{ font: {{ size: 12 }} }},
  interaction: {{ hover: true, tooltipDelay: 200 }},
}};
const network = new vis.Network(container, data, options);

// Community filter checkboxes
const filtersDiv = document.getElementById('filters');
const hiddenComms = new Set();
communities.forEach(c => {{
  const row = document.createElement('div');
  row.className = 'comm-filter';
  row.innerHTML = `<input type="checkbox" checked data-cid="${{c.id}}">
    <span class="comm-dot" style="background:${{c.color}}"></span>${{c.label}}`;
  filtersDiv.appendChild(row);
  row.querySelector('input').addEventListener('change', e => {{
    if (e.target.checked) hiddenComms.delete(c.id); else hiddenComms.add(c.id);
    applyFilters();
  }});
}});

function applyFilters() {{
  const q = document.getElementById('search').value.toLowerCase();
  allNodes.forEach(n => {{
    const hidden = hiddenComms.has(n.community) || (q && !n.label.toLowerCase().includes(q));
    nodes.update({{ id: n.id, hidden }});
  }});
}}

document.getElementById('search').addEventListener('input', applyFilters);
</script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")


def export_wiki(
    G: nx.DiGraph,
    communities: dict[int, list[str]],
    labels: dict[int, str],
    output_dir: Path,
    cohesion: dict[int, float] | None = None,
) -> int:
    """Wrapper for wiki.generate_wiki.

    Args:
        G: NetworkX DiGraph.
        communities: Dict mapping community_id to list of node_ids.
        labels: Dict mapping community_id to human-readable label.
        output_dir: Base output directory.
        cohesion: Optional cohesion scores.

    Returns:
        Number of wiki pages generated.
    """
    return generate_wiki(G, communities, labels, output_dir, cohesion=cohesion)
