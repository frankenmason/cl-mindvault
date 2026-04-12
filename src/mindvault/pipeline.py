"""Pipeline orchestrator: detect -> extract -> graph -> wiki -> index."""

from __future__ import annotations

import json
from pathlib import Path

from mindvault.compile import compile
from mindvault.index import index_markdown, update_index
from mindvault.detect import detect
from mindvault.extract import extract_ast
from mindvault.build import build_graph
from mindvault.cache import get_dirty_files, update_cache


def run(source_dir: Path, output_dir: Path = None, **kwargs) -> dict:
    """Full pipeline orchestrator.

    Args:
        source_dir: Root directory of the project.
        output_dir: Directory for MindVault output (default: source_dir/mindvault-out).
        **kwargs: Additional options passed to sub-steps.

    Returns:
        Dict with stats: {nodes, edges, communities, wiki_pages, index_docs, total_words}.
    """
    source_dir = Path(source_dir)
    if output_dir is None:
        output_dir = source_dir / "mindvault-out"
    output_dir = Path(output_dir)

    # Run compile (detect -> extract -> graph -> cluster -> wiki -> export)
    result = compile(source_dir, output_dir, **kwargs)

    # Detect again to get doc files (compile doesn't expose detection)
    detection = detect(source_dir)

    # Build search index on wiki pages + source documents
    wiki_dir = output_dir / "wiki"
    index_path = output_dir / "search_index.json"
    index_docs = 0
    if wiki_dir.exists():
        index_docs = index_markdown(wiki_dir, index_path)

    # Also index source .md documents for better search coverage
    doc_files = detection["files"].get("document", [])
    if doc_files:
        _index_source_docs(source_dir, doc_files, index_path)
        index_docs += len(doc_files)

    # Index data files (.json, .yaml, .yml) for search coverage
    data_files = detection["files"].get("data", [])
    if data_files:
        _index_data_files(source_dir, data_files, index_path)
        index_docs += len(data_files)

    result["index_docs"] = index_docs
    return result


def _index_source_docs(source_dir: Path, doc_files: list[str], index_path: Path) -> None:
    """Append source documents (.md, .txt, .rst, .docx, .xlsx, .pptx) to the search index.

    For binary Office formats, delegates to mindvault.ingest._extract_text_from_file
    which uses python-docx / openpyxl / python-pptx to pull plain text.
    """
    from mindvault.index import load_index, _tokenize, _extract_title, _extract_headings, _hash_content, _compute_idf
    from mindvault.detect import BINARY_DOCUMENT_EXTS
    from mindvault.ingest import _extract_text_from_file
    import json

    index_data = load_index(index_path)
    docs = index_data.get("docs", {})

    for rel_path in doc_files:
        full_path = source_dir / rel_path
        if not full_path.exists():
            continue
        ext = full_path.suffix.lower()
        content: str | None
        if ext in BINARY_DOCUMENT_EXTS:
            content = _extract_text_from_file(full_path)
        else:
            try:
                content = full_path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, IOError):
                content = None
        if not content:
            continue
        key = f"source/{rel_path}"
        docs[key] = {
            "title": _extract_title(content) or Path(rel_path).stem,
            "headings": _extract_headings(content),
            "tokens": _tokenize(content),
            "hash": _hash_content(content),
        }

    index_data["docs"] = docs
    index_data["doc_count"] = len(docs)
    index_data["idf"] = _compute_idf(docs)
    index_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")


def _flatten_json(obj, prefix: str = "") -> list[str]:
    """Flatten a JSON object into searchable text fragments.

    Extracts all string values and their key paths so that structured data
    (e.g. metadata.json with title, description, tags) becomes searchable.
    """
    fragments: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, str):
                fragments.append(f"{k}: {v}")
            elif isinstance(v, (int, float)):
                fragments.append(f"{k}: {v}")
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, str):
                        fragments.append(item)
                    elif isinstance(item, dict):
                        fragments.extend(_flatten_json(item, key_path))
            elif isinstance(v, dict):
                fragments.extend(_flatten_json(v, key_path))
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, str):
                fragments.append(item)
            elif isinstance(item, dict):
                fragments.extend(_flatten_json(item, prefix))
    return fragments


def _index_data_files(source_dir: Path, data_files: list[str], index_path: Path) -> None:
    """Index data files (.json, .yaml, .yml) into the search index.

    Flattens structured data into searchable text so that metadata,
    configuration, and output files become discoverable via search.
    """
    from mindvault.index import load_index, _tokenize, _hash_content, _compute_idf

    index_data = load_index(index_path)
    docs = index_data.get("docs", {})

    for rel_path in data_files:
        full_path = source_dir / rel_path
        if not full_path.exists():
            continue

        try:
            raw = full_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, IOError):
            continue

        content_hash = _hash_content(raw)
        key = f"data/{rel_path}"

        # Skip if unchanged
        if key in docs and docs[key].get("hash") == content_hash:
            continue

        ext = full_path.suffix.lower()
        title = Path(rel_path).stem
        text_fragments: list[str] = []

        if ext == ".json":
            try:
                obj = json.loads(raw)
                text_fragments = _flatten_json(obj)
                # Use title/name field if available
                if isinstance(obj, dict):
                    title = obj.get("title") or obj.get("name") or title
            except json.JSONDecodeError:
                text_fragments = [raw]
        elif ext in (".yaml", ".yml"):
            try:
                import yaml
                obj = yaml.safe_load(raw)
                if isinstance(obj, (dict, list)):
                    text_fragments = _flatten_json(obj)
                    if isinstance(obj, dict):
                        title = obj.get("title") or obj.get("name") or title
                else:
                    text_fragments = [str(obj)]
            except Exception:
                text_fragments = [raw]
        else:
            text_fragments = [raw]

        content = "\n".join(text_fragments)
        tokens = _tokenize(content)

        if not tokens:
            continue

        docs[key] = {
            "title": title,
            "headings": [],
            "tokens": tokens,
            "hash": content_hash,
        }

    index_data["docs"] = docs
    index_data["doc_count"] = len(docs)
    index_data["idf"] = _compute_idf(docs)
    index_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_incremental(source_dir: Path, output_dir: Path = None) -> dict:
    """Incremental pipeline: only process changed files.

    Extraction is restricted to dirty files, then merged with the existing
    graph.json. Finalization (cluster → wiki → export → report) is delegated
    to the shared ``_finalize_and_export`` helper in compile.py, so this
    function and ``compile()`` stay consistent.

    Args:
        source_dir: Root directory of the project.
        output_dir: Directory for MindVault output.

    Returns:
        Dict with stats: {changed, nodes, edges, communities, wiki_pages, index_docs}
        or {changed: 0} if nothing changed.
    """
    source_dir = Path(source_dir)
    if output_dir is None:
        output_dir = source_dir / "mindvault-out"
    output_dir = Path(output_dir)

    # If output doesn't exist yet, run full pipeline
    graph_path = output_dir / "graph.json"
    if not graph_path.exists():
        return run(source_dir, output_dir)

    # Option A: auto-migrate pre-0.4.0 graph.json to the canonical schema.
    # Passes source_dir as index_root so migrated IDs match a fresh build.
    from mindvault.migrate import migrate_graph_if_needed
    migration = migrate_graph_if_needed(graph_path, index_root=source_dir)
    if migration["status"] == "needs_rebuild":
        # Option E fallback — user was told to rebuild. Fall through to full
        # pipeline so the next run is immediately usable instead of erroring.
        return run(source_dir, output_dir)

    # Detect files
    detection = detect(source_dir)
    code_files = [source_dir / f for f in detection["files"].get("code", [])]
    doc_files = [source_dir / f for f in detection["files"].get("document", [])]
    data_files = [source_dir / f for f in detection["files"].get("data", [])]

    # Check which files changed (code + documents + data)
    dirty_code = get_dirty_files(code_files, output_dir)
    dirty_docs = get_dirty_files(doc_files, output_dir)
    dirty_data = get_dirty_files(data_files, output_dir)
    dirty_files = dirty_code + dirty_docs + dirty_data

    if not dirty_files:
        return {"changed": 0}

    # Extract AST for dirty code files, document structure for dirty doc/data files.
    # source_dir is the canonical index_root so IDs match a full rebuild.
    from mindvault.extract import extract_document_structure
    code_extraction = (
        extract_ast(dirty_code, index_root=source_dir)
        if dirty_code else {"nodes": [], "edges": []}
    )
    dirty_docs_and_data = dirty_docs + dirty_data
    doc_extraction = (
        extract_document_structure(dirty_docs_and_data, index_root=source_dir)
        if dirty_docs_and_data else {"nodes": [], "edges": []}
    )
    extraction = {
        "nodes": code_extraction["nodes"] + doc_extraction["nodes"],
        "edges": code_extraction["edges"] + doc_extraction["edges"],
    }

    # Load existing graph data and merge new extraction with it
    existing_data = json.loads(graph_path.read_text(encoding="utf-8"))
    existing_nodes = {n["id"]: n for n in existing_data.get("nodes", [])}
    existing_links = existing_data.get("links", [])

    # Remove stale nodes from dirty files, then add new/updated ones
    dirty_sources = {str(f) for f in dirty_files}
    existing_nodes = {
        nid: n for nid, n in existing_nodes.items()
        if n.get("source_file") not in dirty_sources
    }
    for node in extraction["nodes"]:
        existing_nodes[node["id"]] = node

    # For edges, remove old edges from dirty files, then add new ones
    kept_links = [
        link for link in existing_links
        if link.get("source_file") not in dirty_sources
    ]
    for edge in extraction["edges"]:
        kept_links.append({
            "source": edge["source"],
            "target": edge["target"],
            "relation": edge.get("relation", ""),
            "confidence": edge.get("confidence", ""),
            "confidence_score": edge.get("confidence_score", 1.0),
            "source_file": edge.get("source_file", ""),
            "weight": edge.get("weight", 1.0),
        })

    # Rebuild graph from merged data
    merged_extraction = {
        "nodes": list(existing_nodes.values()),
        "edges": kept_links,
    }
    G = build_graph(merged_extraction)

    # Finalize: shared helper does cluster → wiki → export → report so that
    # incremental and full builds stay in lock-step (Codex finding #9).
    from mindvault.compile import _finalize_and_export
    stats = _finalize_and_export(
        G, source_dir, output_dir, detection,
        incremental=True, write_report=False,
    )

    # Update search index (incremental path manages this independently of
    # wiki regeneration because only wiki/ changed)
    wiki_dir = output_dir / "wiki"
    index_path = output_dir / "search_index.json"
    index_docs = 0
    if wiki_dir.exists():
        index_docs = update_index(wiki_dir, index_path)

    # Update cache for processed files
    for f in dirty_files:
        update_cache(f, output_dir)

    return {
        "changed": len(dirty_files),
        "nodes": stats["nodes"],
        "edges": stats["edges"],
        "communities": stats["communities"],
        "wiki_pages": stats["wiki_pages"],
        "index_docs": index_docs,
    }
