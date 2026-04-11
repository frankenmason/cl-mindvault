"""End-to-end ingest test on a miniature Obsidian vault.

Locks the 0.3.0 / 0.3.1 full pipeline behavior:
  - recursive walk + SKIP_DIRS (`.obsidian`, `.trash`) exclusion
  - frontmatter parsing with metadata attached to the synthetic file node
  - inline #tag extraction (including Korean and CJK) with code-span stripping
  - first_header_id capture (contains edge from file node → first header only)

If 0.4.0 refactors document identity, these assertions will need deliberate
updates — which is exactly the point of a golden test.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _run_ingest(vault: Path) -> dict:
    """Run `mindvault ingest .` inside vault and return the resulting graph."""
    # Use the CLI entry point so we exercise the full pipeline, not just
    # extract_document_structure in isolation.
    env = os.environ.copy()
    subprocess.run(
        [sys.executable, "-m", "mindvault", "ingest", str(vault)],
        cwd=vault,
        check=True,
        capture_output=True,
        env=env,
    )
    graph_path = vault / "mindvault-out" / "graph.json"
    return json.loads(graph_path.read_text())


class TestObsidianVaultIngest:
    def test_skip_dirs_excluded(self, obsidian_vault_fixture: Path):
        graph = _run_ingest(obsidian_vault_fixture)
        for node in graph["nodes"]:
            src = node.get("source_file", "")
            label = node.get("label", "")
            assert ".obsidian" not in src, f"Obsidian internal leaked: {node}"
            assert ".trash" not in src, f"Trash content leaked: {node}"
            assert label != "Should Be Skipped", f"Trash file node leaked: {node}"

    def test_recursive_subfolder_traversal(self, obsidian_vault_fixture: Path):
        graph = _run_ingest(obsidian_vault_fixture)
        # The subfolder/nested.md must be indexed
        nested_nodes = [
            n for n in graph["nodes"]
            if "nested.md" in n.get("source_file", "")
        ]
        assert nested_nodes, "nested.md in subfolder was not indexed"

    def test_plan_file_node_has_combined_tags(self, obsidian_vault_fixture: Path):
        graph = _run_ingest(obsidian_vault_fixture)
        plan_file = next(
            (n for n in graph["nodes"] if n["id"] == "plan_file"),
            None,
        )
        assert plan_file is not None, "Expected synthetic file node `plan_file`"
        tags = set(plan_file.get("tags", []))

        # Frontmatter tags
        assert {"project", "auth", "2026-q2"} <= tags

        # Inline tags from prose (includes Unicode)
        assert "architecture" in tags  # #architecture outside code spans
        assert "security" in tags       # #security review
        assert "testing" in tags        # #testing tag
        assert "한글" in tags            # Korean Unicode tag
        assert "日本語" in tags          # CJK Unicode tag
        assert "real" in tags           # #real (not hex)

        # Hex colors must NOT be in tags
        assert "fff" not in tags
        assert "ffffff" not in tags

        # Code-span content must NOT be in tags
        assert "define" not in tags     # `#define FOO` was stripped

    def test_plan_file_node_has_metadata(self, obsidian_vault_fixture: Path):
        graph = _run_ingest(obsidian_vault_fixture)
        plan_file = next(n for n in graph["nodes"] if n["id"] == "plan_file")
        meta = plan_file.get("metadata", {})
        assert meta.get("title") == "Auth Rewrite Plan"
        assert meta.get("status") == "in-progress"

    def test_plan_file_label_uses_frontmatter_title(self, obsidian_vault_fixture: Path):
        graph = _run_ingest(obsidian_vault_fixture)
        plan_file = next(n for n in graph["nodes"] if n["id"] == "plan_file")
        assert plan_file["label"] == "Auth Rewrite Plan"

    def test_file_node_contains_first_header_only(self, obsidian_vault_fixture: Path):
        """Regression guard for Codex Finding #6 (fixed in 0.3.1).

        The plan fixture has TWO top-level H1 headers (`Auth Rewrite Plan`
        and `Second Top Level`). The file-level synthetic node must link to
        the first, not the last branch's ancestor.
        """
        graph = _run_ingest(obsidian_vault_fixture)
        # NetworkX JSON uses "links" rather than "edges"
        edges = graph.get("links") or graph.get("edges") or []
        contains_edges = [
            e for e in edges
            if e.get("source") == "plan_file" and e.get("relation") == "contains"
        ]
        assert contains_edges, "plan_file has no `contains` edge"
        targets = {e["target"] for e in contains_edges}
        # First header is `Auth Rewrite Plan` → slugged as `plan_auth_rewrite_plan`
        first_header_targets = [t for t in targets if "auth_rewrite_plan" in t]
        assert first_header_targets, f"Expected first header target, got {targets}"
        # Must NOT target the second top-level section
        assert not any("second_top_level" in t for t in targets), (
            f"file_node should not link to second H1: {targets}"
        )

    def test_nested_note_has_own_file_node(self, obsidian_vault_fixture: Path):
        graph = _run_ingest(obsidian_vault_fixture)
        nested_file = next(
            (n for n in graph["nodes"] if n["id"] == "nested_file"),
            None,
        )
        assert nested_file is not None
        tags = set(nested_file.get("tags", []))
        assert "meta" in tags
        assert "nested-tag" in tags
