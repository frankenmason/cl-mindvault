"""3-layer query: search -> graph traverse -> wiki context -> answer."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from mindvault.search import search as bm25_search


def _is_cjk(char: str) -> bool:
    """Check if a character is CJK."""
    cp = ord(char)
    return (
        (0x3000 <= cp <= 0x9FFF)
        or (0xAC00 <= cp <= 0xD7AF)
        or (0xF900 <= cp <= 0xFAFF)
    )


def _keyword_match(question: str, node_id: str, node_label: str) -> bool:
    """Check if any keyword from the question matches a node.

    Korean/CJK tokens are kept regardless of length.
    English tokens must be > 2 chars.
    """
    import re
    cleaned = re.sub(r'[^\w\s]', ' ', question.lower())
    q_tokens = set()
    for t in cleaned.split():
        if not t:
            continue
        has_cjk = any(_is_cjk(c) for c in t)
        if has_cjk or len(t) > 2:
            q_tokens.add(t)

    label_lower = node_label.lower()
    nid_lower = node_id.lower()
    for token in q_tokens:
        if token in label_lower or token in nid_lower:
            return True
    return False


def _bfs_traverse(graph_data: dict, start_nodes: list[str], depth: int = 2) -> dict:
    """BFS traversal from start_nodes up to given depth."""
    nodes_set = {n["id"] for n in graph_data.get("nodes", [])}
    adj: dict[str, list[tuple[str, dict]]] = {}
    for link in graph_data.get("links", []):
        src = link.get("source", "")
        tgt = link.get("target", "")
        if src in nodes_set and tgt in nodes_set:
            adj.setdefault(src, []).append((tgt, link))
            adj.setdefault(tgt, []).append((src, link))

    visited: set[str] = set()
    neighbors: list[str] = []
    edges: list[dict] = []
    queue: deque[tuple[str, int]] = deque()

    for sn in start_nodes:
        if sn in nodes_set:
            queue.append((sn, 0))
            visited.add(sn)

    while queue:
        node, d = queue.popleft()
        if d >= depth:
            continue
        for neighbor, link in adj.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                neighbors.append(neighbor)
                edges.append(link)
                queue.append((neighbor, d + 1))

    return {"neighbors": neighbors, "edges": edges}


def _dfs_traverse(graph_data: dict, start_nodes: list[str], depth: int = 4) -> dict:
    """DFS traversal from start_nodes up to given depth."""
    nodes_set = {n["id"] for n in graph_data.get("nodes", [])}
    adj: dict[str, list[tuple[str, dict]]] = {}
    for link in graph_data.get("links", []):
        src = link.get("source", "")
        tgt = link.get("target", "")
        if src in nodes_set and tgt in nodes_set:
            adj.setdefault(src, []).append((tgt, link))
            adj.setdefault(tgt, []).append((src, link))

    visited: set[str] = set()
    neighbors: list[str] = []
    edges: list[dict] = []

    def dfs(node: str, d: int) -> None:
        if d >= depth:
            return
        for neighbor, link in adj.get(node, []):
            if neighbor not in visited:
                visited.add(neighbor)
                neighbors.append(neighbor)
                edges.append(link)
                dfs(neighbor, d + 1)

    for sn in start_nodes:
        if sn in nodes_set:
            visited.add(sn)
            dfs(sn, 0)

    return {"neighbors": neighbors, "edges": edges}


def query(question: str, output_dir: Path, mode: str = "bfs", budget: int = 2000) -> dict:
    """3-layer query: search -> graph -> wiki -> answer context.

    Args:
        question: Natural language question.
        output_dir: MindVault output directory containing index, graph, wiki.
        mode: Graph traversal mode — "bfs" or "dfs".
        budget: Maximum token budget for context assembly.

    Returns:
        Dict with keys: search_results, graph_context, wiki_context, tokens_used.
    """
    output_dir = Path(output_dir)

    # === Step 1: Search Layer (0 tokens) ===
    index_path = output_dir / "search_index.json"
    search_results = []
    if index_path.exists():
        search_results = bm25_search(question, index_path, top_k=3)

    # === Step 2: Graph Layer ===
    graph_path = output_dir / "graph.json"
    graph_data = {}
    matched_nodes: list[str] = []
    graph_context = {
        "matched_nodes": [],
        "neighbors": [],
        "edges": [],
        "communities": [],
    }

    if graph_path.exists():
        graph_data = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes = graph_data.get("nodes", [])

        # Find nodes matching question keywords
        for node in nodes:
            nid = node.get("id", "")
            label = node.get("label", "")
            if _keyword_match(question, nid, label):
                matched_nodes.append(nid)

        # Traverse graph
        if matched_nodes:
            if mode == "dfs":
                traversal = _dfs_traverse(graph_data, matched_nodes, depth=4)
            else:
                traversal = _bfs_traverse(graph_data, matched_nodes, depth=2)

            # Find communities for matched nodes
            communities_data = graph_data.get("communities", {})
            matched_communities = []
            for cid, members in communities_data.items():
                for mn in matched_nodes:
                    if mn in members:
                        matched_communities.append(cid)
                        break

            graph_context = {
                "matched_nodes": matched_nodes,
                "neighbors": traversal["neighbors"],
                "edges": traversal["edges"],
                "communities": matched_communities,
            }

    # === Step 3: Wiki Layer ===
    wiki_dir = output_dir / "wiki"
    wiki_context = ""
    # Reserve ~200 tokens for graph edges, rest for wiki
    graph_edge_chars = sum(len(str(e)) for e in graph_context.get("edges", []))
    graph_tokens = graph_edge_chars // 4
    wiki_token_budget = budget - graph_tokens - 10  # small margin
    if wiki_token_budget < 100:
        wiki_token_budget = 100
    char_limit = wiki_token_budget * 4

    if wiki_dir.exists():
        # Collect wiki pages from search results
        wiki_paths = []
        for sr in search_results:
            wp = wiki_dir / sr["path"]
            if wp.exists():
                wiki_paths.append(wp)

        # Also look for wiki pages matching graph communities
        if not wiki_paths:
            # Fallback: try to find any wiki pages matching keywords
            for md_file in sorted(wiki_dir.glob("*.md")):
                if md_file.name == "INDEX.md":
                    continue
                wiki_paths.append(md_file)
                if len(wiki_paths) >= 3:
                    break

        # Read wiki content up to budget
        parts = []
        total_chars = 0
        for wp in wiki_paths:
            try:
                content = wp.read_text(encoding="utf-8")
                if total_chars + len(content) > char_limit:
                    remaining = char_limit - total_chars
                    if remaining > 100:
                        parts.append(content[:remaining] + "...")
                        total_chars += remaining
                    break
                parts.append(content)
                total_chars += len(content)
            except (OSError, IOError):
                continue

        wiki_context = "\n\n---\n\n".join(parts)

    # Calculate approximate tokens
    total_text = wiki_context
    for edge in graph_context.get("edges", []):
        total_text += str(edge)
    tokens_used = len(total_text) // 4

    return {
        "search_results": search_results,
        "graph_context": graph_context,
        "wiki_context": wiki_context,
        "tokens_used": tokens_used,
    }
