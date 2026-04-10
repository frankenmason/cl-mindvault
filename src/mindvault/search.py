"""Search layer — BM25 search (local, zero tokens)."""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

from .index import index_markdown, load_index


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
    cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
    tokens = []
    for t in cleaned.split():
        if not t:
            continue
        has_cjk = any(_is_cjk(c) for c in t)
        if has_cjk or len(t) > 2:
            tokens.append(t)
    return tokens


def _snippet(content_tokens: list[str], query_tokens: set[str], width: int = 30) -> str:
    """Build a snippet around the first matching token.

    Joins tokens back to text, finds first query match position,
    returns +-width chars around it. Falls back to first 100 chars.
    """
    text = " ".join(content_tokens)
    for qt in query_tokens:
        pos = text.find(qt)
        if pos >= 0:
            start = max(0, pos - width)
            end = min(len(text), pos + len(qt) + width)
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(text) else ""
            return prefix + text[start:end] + suffix
    # No match — first 100 chars
    return text[:100] + ("..." if len(text) > 100 else "")


def search(query: str, index_path: Path, top_k: int = 5) -> list[dict]:
    """BM25 search over a markdown index.

    Args:
        query: Search query string.
        index_path: Path to the search index JSON.
        top_k: Number of top results to return.

    Returns:
        List of dicts: [{path, title, score, snippet, headings}, ...].
    """
    index_path = Path(index_path)
    index_data = load_index(index_path)
    docs = index_data.get("docs", {})
    idf = index_data.get("idf", {})

    if not docs:
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    # BM25 parameters
    k1 = 1.5
    b = 0.75

    # Average document length
    doc_lengths = {path: len(doc["tokens"]) for path, doc in docs.items()}
    avgdl = sum(doc_lengths.values()) / len(doc_lengths) if doc_lengths else 1.0

    results = []

    for path, doc in docs.items():
        tokens = doc["tokens"]
        dl = len(tokens)
        if dl == 0:
            continue

        tf_counts = Counter(tokens)
        score = 0.0

        for qt in query_tokens:
            # Exact match first
            tf = tf_counts.get(qt, 0)
            idf_val = idf.get(qt)

            # CJK fuzzy: if no exact match, try prefix/substring matching
            if tf == 0 and any(_is_cjk(c) for c in qt):
                for doc_token, count in tf_counts.items():
                    if doc_token.startswith(qt) or qt in doc_token:
                        tf += count
                        if idf_val is None:
                            idf_val = idf.get(doc_token)

            if tf == 0 or idf_val is None:
                continue
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * dl / avgdl)
            score += idf_val * numerator / denominator

        if score > 0:
            results.append({
                "path": path,
                "title": doc["title"],
                "score": round(score, 4),
                "snippet": _snippet(tokens, set(query_tokens)),
                "headings": doc.get("headings", []),
            })

    # Sort by score descending
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]


def build_index(docs_dir: Path, index_path: Path) -> int:
    """Index all markdown files (wrapper for index.index_markdown).

    Args:
        docs_dir: Directory containing markdown files to index.
        index_path: Path to write the search index.

    Returns:
        Number of documents indexed.
    """
    return index_markdown(Path(docs_dir), Path(index_path))
