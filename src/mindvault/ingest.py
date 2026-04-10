"""External source ingestion — files, URLs, directories."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

from mindvault.llm import detect_llm, call_llm, estimate_cost, confirm_api_usage

_EXTRACTION_PROMPT = """Extract key concepts and relationships from this text.
Return JSON only:
{
  "nodes": [{"id": "slug_name", "label": "Human Name", "file_type": "document", "source_file": "path"}],
  "edges": [{"source": "id1", "target": "id2", "relation": "references|implements|related_to", "confidence": "EXTRACTED|INFERRED", "confidence_score": 0.8}]
}

Rules:
- Extract named concepts, entities, technologies, decisions
- EXTRACTED: explicitly stated relationship
- INFERRED: reasonable inference
- Keep nodes under 30 per document
- Keep edges under 50 per document"""


def _extract_text_from_file(file_path: Path) -> str | None:
    """Extract text content from a file based on extension."""
    ext = file_path.suffix.lower()

    if ext in (".md", ".txt", ".rst"):
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, IOError):
            return None

    if ext == ".pdf":
        return _extract_pdf_text(file_path)

    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        # Image: skip (vision API is a Known Gap)
        return None

    # Unknown extension: try reading as text
    try:
        return file_path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, IOError, UnicodeDecodeError):
        return None


def _extract_pdf_text(file_path: Path) -> str | None:
    """Extract text from PDF using pdftotext, or skip."""
    try:
        result = subprocess.run(
            ["pdftotext", str(file_path), "-"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _strip_html(html: str) -> str:
    """Strip HTML to plain text (simple tag removal)."""
    # Remove script and style blocks
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    html = re.sub(r"\s+", " ", html).strip()
    return html


def _url_to_slug(url: str) -> str:
    """Convert URL to a filesystem-safe slug."""
    # Remove protocol
    slug = re.sub(r"^https?://", "", url)
    # Replace non-alphanumeric with underscore
    slug = re.sub(r"[^a-zA-Z0-9]", "_", slug)
    # Collapse underscores and trim
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:100]


def _llm_extract(text: str, source_file: str, provider: dict) -> dict:
    """Call LLM for concept extraction, return {nodes, edges} or empty."""
    if not text or not text.strip():
        return {"nodes": [], "edges": []}

    # Truncate text to max_tokens_per_file equivalent chars
    from mindvault.config import get as cfg_get
    max_tokens = cfg_get("max_tokens_per_file", 4000)
    max_chars = max_tokens * 4  # rough token-to-char ratio
    if len(text) > max_chars:
        text = text[:max_chars]

    response = call_llm(_EXTRACTION_PROMPT, text, provider)
    if not response:
        return {"nodes": [], "edges": []}

    # Parse JSON from response (may be wrapped in markdown code block)
    return _parse_llm_json(response, source_file)


def _parse_llm_json(response: str, source_file: str) -> dict:
    """Parse LLM JSON response, handling markdown code blocks."""
    # Strip markdown code block if present
    cleaned = response.strip()
    if cleaned.startswith("```"):
        # Remove first and last lines (```json and ```)
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned)
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        # Ensure source_file is set on all nodes
        for node in nodes:
            if "source_file" not in node or not node["source_file"]:
                node["source_file"] = source_file
            if "file_type" not in node:
                node["file_type"] = "document"

        # Ensure required edge fields
        for edge in edges:
            if "confidence" not in edge:
                edge["confidence"] = "INFERRED"
            if "confidence_score" not in edge:
                edge["confidence_score"] = 0.7
            if "source_file" not in edge:
                edge["source_file"] = source_file
            if "weight" not in edge:
                edge["weight"] = 1.0

        return {"nodes": nodes, "edges": edges}
    except (json.JSONDecodeError, KeyError, TypeError):
        return {"nodes": [], "edges": []}


def ingest_file(file_path: Path, output_dir: Path) -> dict:
    """Ingest a single file: copy to sources/, extract text, LLM extract, merge.

    Returns:
        Dict with keys: nodes (int), edges (int), source (str), or {skipped: True}.
    """
    file_path = Path(file_path).resolve()
    output_dir = Path(output_dir)

    if not file_path.exists():
        return {"error": f"File not found: {file_path}"}

    # Copy to sources/
    sources_dir = output_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    dest = sources_dir / file_path.name
    shutil.copy2(file_path, dest)

    # Extract text
    text = _extract_text_from_file(file_path)
    if text is None:
        return {"skipped": True, "source": str(file_path), "reason": "unsupported format"}

    # Detect LLM
    provider = detect_llm()
    if provider["provider"] is None:
        return {"skipped": True, "source": str(file_path), "reason": "no LLM available"}

    # Consent for API
    if not provider["is_local"]:
        cost = estimate_cost(text, provider)
        if not confirm_api_usage(provider, cost):
            return {"skipped": True, "source": str(file_path), "reason": "API usage declined"}

    # LLM extraction
    result = _llm_extract(text, str(file_path), provider)

    return {
        "nodes": len(result["nodes"]),
        "edges": len(result["edges"]),
        "source": str(file_path),
        "extraction": result,
    }


def ingest_url(url: str, output_dir: Path) -> dict:
    """Ingest a URL: fetch, strip HTML, save as .md, then extract.

    Returns:
        Dict with keys: nodes (int), edges (int), source (str).
    """
    output_dir = Path(output_dir)
    sources_dir = output_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    # Fetch URL
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "MindVault/0.1 (knowledge extraction)"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        html = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return {"error": f"Failed to fetch URL: {e}"}

    # Strip HTML to text
    text = _strip_html(html)

    # Save as markdown
    slug = _url_to_slug(url)
    md_path = sources_dir / f"{slug}.md"
    md_path.write_text(f"# {url}\n\n{text}", encoding="utf-8")

    # Now ingest the saved file
    return ingest_file(md_path, output_dir)


def ingest(source: str, output_dir: Path) -> dict:
    """Entry point: detect file vs URL vs directory and dispatch.

    Args:
        source: File path, URL, or directory path.
        output_dir: MindVault output directory.

    Returns:
        Dict with ingestion results.
    """
    output_dir = Path(output_dir)

    # URL detection
    if source.startswith("http://") or source.startswith("https://"):
        return ingest_url(source, output_dir)

    path = Path(source)
    if not path.exists():
        return {"error": f"Source not found: {source}"}

    if path.is_file():
        return ingest_file(path, output_dir)

    if path.is_dir():
        # Ingest all files in directory
        total_nodes = 0
        total_edges = 0
        files_processed = 0
        for child in sorted(path.iterdir()):
            if child.is_file() and not child.name.startswith("."):
                result = ingest_file(child, output_dir)
                if not result.get("skipped") and not result.get("error"):
                    total_nodes += result.get("nodes", 0)
                    total_edges += result.get("edges", 0)
                    files_processed += 1
        return {
            "nodes": total_nodes,
            "edges": total_edges,
            "files_processed": files_processed,
            "source": str(path),
        }

    return {"error": f"Unknown source type: {source}"}
