"""Multi-AI tool integration — detect AI tools and install MindVault blocks."""

from __future__ import annotations

from pathlib import Path


AI_TOOLS = [
    {
        "name": "Claude Code",
        "detect_files": ["CLAUDE.md"],
        "rules_file": "CLAUDE.md",
        "type": "append_section",
    },
    {
        "name": "Cursor",
        "detect_files": [".cursorrules", ".cursor/rules"],
        "rules_file": ".cursorrules",
        "type": "create_or_append",
    },
    {
        "name": "GitHub Copilot",
        "detect_files": [".github/copilot-instructions.md"],
        "rules_file": ".github/copilot-instructions.md",
        "type": "create_or_append",
    },
    {
        "name": "Windsurf",
        "detect_files": [".windsurfrules"],
        "rules_file": ".windsurfrules",
        "type": "create_or_append",
    },
    {
        "name": "Gemini Code Assist",
        "detect_files": [".gemini/settings.json", ".gemini/styleguide.md"],
        "rules_file": ".gemini/styleguide.md",
        "type": "create_or_append",
    },
    {
        "name": "Cline",
        "detect_files": [".clinerules"],
        "rules_file": ".clinerules",
        "type": "create_or_append",
    },
    {
        "name": "Aider",
        "detect_files": [".aider.conf.yml", ".aiderignore"],
        "rules_file": "CONVENTIONS.md",
        "type": "create_or_append",
    },
]

CLAUDE_MD_SECTION = """\

## MindVault

MindVault knowledge base is available. Before answering codebase questions:

1. Run `mindvault query "<question>"` to get context from the knowledge graph
2. Use the search results, graph context, and wiki context in your answer
3. If mindvault-out/ doesn't exist, run `mindvault ingest .` first

For global cross-project queries, use `mindvault query "<question>" --global`
"""

GENERIC_RULES = """\

# MindVault Knowledge Base

This project has a MindVault knowledge base. Before answering codebase questions,
run `mindvault query "<question>"` in the terminal to get context from the
knowledge graph, wiki, and search index. Use the output to inform your answer.

If the `mindvault-out/` directory doesn't exist, run `mindvault ingest .` first
to build the knowledge base.

For cross-project queries: `mindvault query "<question>" --global`
"""


def detect_ai_tools(project_dir: Path) -> list[dict]:
    """Detect AI tools by checking for their rules/config files.

    Returns list of detected tool dicts, each with an added 'detected_file' key.
    """
    detected = []
    for tool in AI_TOOLS:
        for detect_file in tool["detect_files"]:
            path = project_dir / detect_file
            if path.exists():
                result = dict(tool)
                result["detected_file"] = detect_file
                detected.append(result)
                break
    return detected


def install_integration(project_dir: Path, tool: dict) -> bool:
    """Install MindVault block into a tool's rules file.

    Returns True if installed, False if already exists or failed.
    """
    rules_path = project_dir / tool["rules_file"]

    # Check if MindVault block already exists
    if rules_path.exists():
        content = rules_path.read_text(encoding="utf-8")
        if "MindVault" in content:
            return False
    else:
        content = ""

    # Ensure parent directory exists
    rules_path.parent.mkdir(parents=True, exist_ok=True)

    if tool["type"] == "append_section":
        # Claude Code: append ## MindVault section
        content += CLAUDE_MD_SECTION
    else:
        # Generic: append # MindVault Knowledge Base block
        content += GENERIC_RULES

    rules_path.write_text(content, encoding="utf-8")
    return True


def install_all_integrations(project_dir: Path) -> list[dict]:
    """Detect all AI tools and install MindVault blocks.

    Returns list of dicts with 'name' and 'status' keys.
    """
    detected = detect_ai_tools(project_dir)
    results = []

    for tool in detected:
        rules_path = project_dir / tool["rules_file"]

        # Check if already exists before installing
        if rules_path.exists() and "MindVault" in rules_path.read_text(encoding="utf-8"):
            results.append({"name": tool["name"], "status": "already_exists"})
            continue

        try:
            installed = install_integration(project_dir, tool)
            if installed:
                # If the file existed before, it was "updated"; if created new, "created"
                # But since we only install for detected tools, the detect file exists
                # The rules_file might be different from detect_file though
                results.append({"name": tool["name"], "status": "installed"})
            else:
                results.append({"name": tool["name"], "status": "already_exists"})
        except Exception:
            results.append({"name": tool["name"], "status": "failed"})

    return results
