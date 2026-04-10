"""Markdown auto-indexing for the search layer."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path


def _is_cjk(char: str) -> bool:
    """Check if a character is CJK (Chinese/Japanese/Korean)."""
    cp = ord(char)
    return (
        (0x3000 <= cp <= 0x9FFF)
        or (0xAC00 <= cp <= 0xD7AF)  # Hangul Syllables
        or (0xF900 <= cp <= 0xFAFF)
    )


def _tokenize(text: str) -> list[str]:
    """Tokenize text for BM25. Handles Korean/CJK and English.

    - Strips punctuation
    - English tokens: remove if len <= 2
    - Korean/CJK tokens: keep all (1-char is meaningful)
    """
    import re
    # Strip punctuation, keep alphanumeric + CJK + whitespace
    cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
    tokens = []
    for t in cleaned.split():
        if not t:
            continue
        has_cjk = any(_is_cjk(c) for c in t)
        if has_cjk or len(t) > 2:
            tokens.append(t)
    return tokens


def _extract_title(text: str) -> str | None:
    """Extract first # header from markdown text."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    return None


def _extract_headings(text: str) -> list[str]:
    """Extract all ## and ### headings."""
    headings = []
    for line in text.splitlines():
        stripped = line.strip()
        m = re.match(r"^(#{2,3})\s+(.+)$", stripped)
        if m:
            headings.append(stripped)
    return headings


def _hash_content(text: str) -> str:
    """SHA256 hex digest of content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compute_idf(docs: dict) -> dict[str, float]:
    """Compute IDF: log(N / (1 + df)) for all tokens across all docs."""
    n = len(docs)
    if n == 0:
        return {}
    # df = number of docs containing each token
    df: Counter = Counter()
    for doc in docs.values():
        unique_tokens = set(doc["tokens"])
        for token in unique_tokens:
            df[token] += 1
    return {token: math.log(n / (1 + count)) for token, count in df.items()}


def index_markdown(docs_dir: Path, index_path: Path) -> int:
    """Build a search index from markdown files.

    Args:
        docs_dir: Directory containing markdown files.
        index_path: Path to store the index as JSON.

    Returns:
        Number of files indexed.
    """
    docs_dir = Path(docs_dir)
    index_path = Path(index_path)

    md_files = sorted(docs_dir.rglob("*.md"))
    docs = {}

    for md_file in md_files:
        rel_path = str(md_file.relative_to(docs_dir))
        content = md_file.read_text(encoding="utf-8")
        title = _extract_title(content) or md_file.stem
        tokens = _tokenize(content)
        headings = _extract_headings(content)
        content_hash = _hash_content(content)

        docs[rel_path] = {
            "title": title,
            "headings": headings,
            "tokens": tokens,
            "hash": content_hash,
        }

    idf = _compute_idf(docs)

    index_data = {
        "version": 1,
        "doc_count": len(docs),
        "docs": docs,
        "idf": idf,
    }

    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return len(docs)


def update_index(docs_dir: Path, index_path: Path) -> int:
    """Incrementally update the index for changed/deleted files.

    Args:
        docs_dir: Directory containing markdown files.
        index_path: Path to the existing index.

    Returns:
        Number of files re-indexed.
    """
    docs_dir = Path(docs_dir)
    index_path = Path(index_path)

    existing = load_index(index_path)
    old_docs = existing.get("docs", {})

    md_files = sorted(docs_dir.rglob("*.md"))
    current_paths = set()
    updated_count = 0

    for md_file in md_files:
        rel_path = str(md_file.relative_to(docs_dir))
        current_paths.add(rel_path)
        content = md_file.read_text(encoding="utf-8")
        content_hash = _hash_content(content)

        if rel_path in old_docs and old_docs[rel_path]["hash"] == content_hash:
            continue  # unchanged

        # New or changed file
        title = _extract_title(content) or md_file.stem
        tokens = _tokenize(content)
        headings = _extract_headings(content)

        old_docs[rel_path] = {
            "title": title,
            "headings": headings,
            "tokens": tokens,
            "hash": content_hash,
        }
        updated_count += 1

    # Remove deleted files
    deleted = set(old_docs.keys()) - current_paths
    for d in deleted:
        del old_docs[d]
        updated_count += 1

    # Recompute IDF
    idf = _compute_idf(old_docs)

    index_data = {
        "version": 1,
        "doc_count": len(old_docs),
        "docs": old_docs,
        "idf": idf,
    }

    index_path.write_text(json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8")

    return updated_count


def load_index(index_path: Path) -> dict:
    """Load index from JSON. Returns empty index if file doesn't exist."""
    index_path = Path(index_path)
    if not index_path.exists():
        return {"version": 1, "doc_count": 0, "docs": {}, "idf": {}}
    return json.loads(index_path.read_text(encoding="utf-8"))
