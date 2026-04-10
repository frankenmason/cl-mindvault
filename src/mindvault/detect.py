"""File detection — classify files by type, skip irrelevant directories."""

from __future__ import annotations

import os
from pathlib import Path

SKIP_DIRS = {
    "node_modules", ".git", "dist", "out", "__pycache__", "build",
    ".next", ".venv", "venv", ".tox", "egg-info",
    ".github", "mindvault-out", "worktrees",
    "coverage", ".nyc_output", ".cache", ".turbo",
    "ios", "android", "Pods", ".expo", ".dart_tool",
    "macos", "windows", "linux", "web",
}

EXT_MAP: dict[str, str] = {}

_CODE_EXTS = (
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs",
    ".go", ".rs", ".java", ".swift", ".kt", ".kts",
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp",
    ".rb", ".cs", ".scala", ".php", ".lua",
)
for _e in _CODE_EXTS:
    EXT_MAP[_e] = "code"

for _e in (".md", ".txt", ".rst"):
    EXT_MAP[_e] = "document"

for _e in (".pdf",):
    EXT_MAP[_e] = "paper"

for _e in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
    EXT_MAP[_e] = "image"


def detect(path: Path) -> dict:
    """Detect files by type.

    Skips: node_modules, .git, dist, out, __pycache__, build, .next, .venv, venv, .tox, egg-info

    Args:
        path: Root directory to scan.

    Returns:
        Dict with keys: files, total_files, total_words, skipped_dirs.
    """
    files: dict[str, list[str]] = {"code": [], "document": [], "paper": [], "image": []}
    total_words = 0
    skipped_dirs = 0

    for dirpath, dirnames, filenames in os.walk(path):
        # Filter out skipped directories in-place
        original_count = len(dirnames)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        skipped_dirs += original_count - len(dirnames)

        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            category = EXT_MAP.get(ext)
            if category is None:
                continue

            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, path)
            files[category].append(rel_path)

            if category in ("code", "document"):
                try:
                    with open(full_path, "r", errors="ignore") as f:
                        content = f.read()
                    total_words += len(content.split())
                except (OSError, IOError):
                    pass

    total_files = sum(len(v) for v in files.values())
    return {
        "files": files,
        "total_files": total_files,
        "total_words": total_words,
        "skipped_dirs": skipped_dirs,
    }
