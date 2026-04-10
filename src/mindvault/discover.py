"""Auto-detect projects under a root directory via BFS walk."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from mindvault.detect import SKIP_DIRS

PROJECT_MARKERS = {
    "package.json",
    "pyproject.toml",
    "setup.py",
    "Cargo.toml",
    "go.mod",
    "pubspec.yaml",
    "build.gradle",
    "build.gradle.kts",
    "Podfile",
    "Gemfile",
    "composer.json",
    "CMakeLists.txt",
    "Makefile",
    "CLAUDE.md",
}

TYPE_MAP = {
    "pubspec.yaml": "Flutter",
    "pyproject.toml": "Python",
    "setup.py": "Python",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "build.gradle": "Android/Gradle",
    "build.gradle.kts": "Android/Gradle",
    "Podfile": "iOS",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "CMakeLists.txt": "C/C++",
}


def _infer_type_from_package_json(path: Path) -> str:
    """Read package.json and infer project type from dependencies."""
    pkg_path = path / "package.json"
    if not pkg_path.exists():
        return "Node.js"
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, OSError):
        return "Node.js"

    deps = {}
    deps.update(data.get("dependencies", {}))
    deps.update(data.get("devDependencies", {}))

    if "next" in deps:
        return "Next.js"
    if "react-native" in deps or "expo" in deps:
        return "Expo/React Native"
    if "remotion" in deps:
        return "Remotion"
    if "react" in deps:
        return "React"
    return "Node.js"


def _infer_type(path: Path, markers: list[str]) -> str:
    """Infer project type from discovered markers."""
    # Check non-package.json markers first (more specific)
    for marker in markers:
        if marker in TYPE_MAP and TYPE_MAP[marker] is not None:
            return TYPE_MAP[marker]

    # package.json needs deeper inspection
    if "package.json" in markers:
        return _infer_type_from_package_json(path)

    # CLAUDE.md alone or Makefile alone
    if "Makefile" in markers:
        return "Make"
    return "Unknown"


def discover_projects(root: Path, max_depth: int = 4) -> list[dict]:
    """BFS walk from root up to max_depth, detecting projects by marker files.

    Once a project is found at a directory, its subdirectories are NOT explored
    (no nested projects).

    Args:
        root: Root directory to scan.
        max_depth: Maximum BFS depth (default 4).

    Returns:
        List of dicts sorted by name, each with keys: name, path, type, markers.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        return []

    projects: list[dict] = []
    project_paths: set[Path] = set()

    # BFS queue: (directory, depth)
    queue: deque[tuple[Path, int]] = deque()
    queue.append((root, 0))

    while queue:
        current, depth = queue.popleft()

        # Skip directories in SKIP_DIRS
        if current.name in SKIP_DIRS and current != root:
            continue

        # Check if this directory is inside an already-discovered project
        is_nested = False
        for pp in project_paths:
            try:
                current.relative_to(pp)
                is_nested = True
                break
            except ValueError:
                pass
        if is_nested:
            continue

        # Check for project markers
        found_markers = []
        for marker in sorted(PROJECT_MARKERS):
            if (current / marker).exists():
                found_markers.append(marker)

        if found_markers and current != root:
            # This is a project
            proj_type = _infer_type(current, found_markers)
            projects.append({
                "name": current.name,
                "path": current,
                "type": proj_type,
                "markers": found_markers,
            })
            project_paths.add(current)
            # Don't explore subdirectories of this project
            continue

        # Explore subdirectories if within depth
        if depth < max_depth:
            try:
                children = sorted(current.iterdir())
            except PermissionError:
                continue
            for child in children:
                if child.is_dir() and child.name not in SKIP_DIRS:
                    queue.append((child, depth + 1))

    # Sort by name
    projects.sort(key=lambda p: p["name"])
    return projects
