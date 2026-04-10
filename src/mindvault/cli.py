"""CLI entry point for MindVault."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from mindvault import __version__


def cmd_install(args) -> None:
    """mindvault install — AI tool detection + integration + skill registration + git hook."""
    from mindvault.hooks import install_git_hook
    from mindvault.integrations import detect_ai_tools, install_all_integrations, AI_TOOLS

    project_root = Path(args.path).resolve()

    # 1. Detect AI tools
    print("Detecting AI tools...")
    detected = detect_ai_tools(project_root)
    detected_names = {t["name"] for t in detected}
    for tool in AI_TOOLS:
        if tool["name"] in detected_names:
            # Find the detected_file for this tool
            det = next(t for t in detected if t["name"] == tool["name"])
            print(f"  \u2713 {tool['name']} ({det['detected_file']} found)")
        else:
            print(f"  \u2717 {tool['name']} (not detected)")

    # 2. Install integrations
    print("\nInstalling integrations...")
    if detected:
        integration_results = install_all_integrations(project_root)
        for r in integration_results:
            if r["status"] == "installed":
                # Find the rules_file for this tool
                tool = next(t for t in AI_TOOLS if t["name"] == r["name"])
                print(f"  \u2713 {r['name']} \u2014 {tool['rules_file']} updated")
            elif r["status"] == "already_exists":
                print(f"  \u2713 {r['name']} \u2014 already configured (skip)")
            else:
                print(f"  \u2717 {r['name']} \u2014 {r['status']}")

    # 3. Copy SKILL.md to ~/.claude/skills/mindvault/
    skill_src = Path(__file__).parent.parent.parent / "skill" / "SKILL.md"
    skill_dst_dir = Path.home() / ".claude" / "skills" / "mindvault"
    if skill_src.exists():
        skill_dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_src, skill_dst_dir / "SKILL.md")
        print(f"  \u2713 Claude Code \u2014 Skill registered (~/.claude/skills/mindvault/)")
    else:
        print("  \u2717 Skill: SKILL.md not found (skip)")

    # 4. Install git hook if in a git repo
    if (project_root / ".git").exists():
        ok = install_git_hook(project_root)
        if ok:
            print(f"  \u2713 Git hook \u2014 post-commit installed")
        else:
            print(f"  \u2717 Git hook \u2014 installation failed")
    else:
        print(f"  \u2717 Git hook \u2014 not a git repo (skip)")

    # 5. Install auto-context prompt hook
    from mindvault.hooks import install_prompt_hook
    if install_prompt_hook():
        print(f"  \u2713 Auto-context hook \u2014 installed (AI auto-queries MindVault)")
    else:
        print(f"  \u2717 Auto-context hook \u2014 installation failed")

    print("\nMindVault is ready. Run `mindvault ingest .` to build your knowledge base.")


def cmd_query(args) -> None:
    """mindvault query "question" — 3-layer query."""
    from mindvault.query import query

    if getattr(args, "use_global", False):
        output_dir = Path.home() / ".mindvault"
    elif hasattr(args, "output_dir") and args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = Path("mindvault-out")

    if not output_dir.exists():
        print(f"No MindVault data found at {output_dir}. Run `mindvault` or `/mindvault .` first.")
        sys.exit(1)

    result = query(args.question, output_dir, mode=args.mode, budget=args.budget)

    # Format output
    print(f"\n=== Search Results (0 tokens) ===")
    if result["search_results"]:
        for i, sr in enumerate(result["search_results"], 1):
            print(f"  {i}. [{sr['title']}] (score: {sr['score']:.2f})")
            print(f"     {sr['snippet'][:80]}")
    else:
        print("  (no results)")

    print(f"\n=== Graph Context ===")
    gc = result["graph_context"]
    if gc["matched_nodes"]:
        print(f"  Matched: {', '.join(gc['matched_nodes'][:10])}")
        if len(gc["matched_nodes"]) > 10:
            print(f"  ... and {len(gc['matched_nodes']) - 10} more")
    else:
        print("  (no matching nodes)")

    if gc["neighbors"]:
        # Show a few neighbor relationships
        for edge in gc["edges"][:5]:
            src = edge.get("source", "?")
            tgt = edge.get("target", "?")
            rel = edge.get("relation", "->")
            print(f"  {src} --{rel}--> {tgt}")
        if len(gc["edges"]) > 5:
            print(f"  ... and {len(gc['edges']) - 5} more edges")

    tokens = result["tokens_used"]
    wiki_len = len(result["wiki_context"])
    print(f"\n=== Wiki Context (est. ~{tokens} tokens) ===")
    if wiki_len > 0:
        # Show first 500 chars
        preview = result["wiki_context"][:500]
        if wiki_len > 500:
            preview += f"\n... ({wiki_len - 500} more chars)"
        print(preview)
    else:
        print("  (no wiki context)")

    print(f"\nTotal tokens used: {tokens}")


def cmd_ingest(args) -> None:
    """mindvault ingest <path|url> — add new source and run incremental update."""
    source = args.path

    # Check if it's a URL
    if source.startswith("http://") or source.startswith("https://"):
        from mindvault.ingest import ingest
        output_dir = Path("mindvault-out")
        print(f"Ingesting URL: {source}")
        result = ingest(source, output_dir)
        print(f"Result: {result}")
        return

    source_path = Path(source).resolve()
    output_dir = Path("mindvault-out")

    if not source_path.exists():
        print(f"Error: {source_path} does not exist.")
        sys.exit(1)

    # Check if it's a non-code file (document, pdf, etc.)
    ext = source_path.suffix.lower()
    if source_path.is_file() and ext in (".md", ".txt", ".rst", ".pdf"):
        from mindvault.ingest import ingest_file
        print(f"Ingesting file: {source_path}")
        result = ingest_file(source_path, output_dir)
        print(f"Result: {result}")
        return

    from mindvault.pipeline import run_incremental
    print(f"Ingesting: {source_path}")
    result = run_incremental(source_path, output_dir)
    print(f"Result: {result}")


def cmd_lint(args) -> None:
    """mindvault lint — wiki + graph consistency check."""
    from mindvault.lint import lint_wiki, lint_graph

    output_dir = Path(args.path) if args.path != ".mindvault" else Path("mindvault-out")
    wiki_dir = output_dir / "wiki"
    graph_path = output_dir / "graph.json"

    if not output_dir.exists():
        print(f"No MindVault data found at {output_dir}. Run `mindvault` or `/mindvault .` first.")
        sys.exit(1)

    print("=== Wiki Lint ===")
    wiki_result = lint_wiki(wiki_dir, graph_path)
    print(f"  Total pages: {wiki_result['total_pages']}")
    print(f"  Broken links: {len(wiki_result['broken_links'])}")
    if wiki_result["broken_links"][:5]:
        for bl in wiki_result["broken_links"][:5]:
            print(f"    - {bl['file']}: [[{bl['link']}]]")
        if len(wiki_result["broken_links"]) > 5:
            print(f"    ... and {len(wiki_result['broken_links']) - 5} more")
    print(f"  Orphan pages: {len(wiki_result['orphan_pages'])}")
    if wiki_result["orphan_pages"][:5]:
        for op in wiki_result["orphan_pages"][:5]:
            print(f"    - {op}")

    print("\n=== Graph Lint ===")
    graph_result = lint_graph(graph_path)
    print(f"  Total nodes: {graph_result['total_nodes']}")
    print(f"  Total edges: {graph_result['total_edges']}")
    print(f"  Isolated nodes: {len(graph_result['isolated_nodes'])}")
    print(f"  Ambiguous edges: {graph_result['ambiguous_edges']}")


def cmd_config(args) -> None:
    """mindvault config — manage configuration."""
    from mindvault.config import load_config, set as set_config

    action = args.config_action

    if action == "show":
        cfg = load_config()
        print("=== MindVault Configuration ===")
        for k, v in cfg.items():
            print(f"  {k}: {v}")
        return

    if action == "llm":
        if not args.value:
            from mindvault.config import get as get_config
            print(f"llm_endpoint: {get_config('llm_endpoint')}")
        else:
            set_config("llm_endpoint", args.value)
            print(f"llm_endpoint set to: {args.value}")
        return

    if action == "auto-approve":
        if not args.value:
            from mindvault.config import get as get_config
            print(f"auto_approve_api: {get_config('auto_approve_api')}")
        else:
            val = args.value.lower() in ("true", "1", "yes")
            set_config("auto_approve_api", val)
            print(f"auto_approve_api set to: {val}")
        return

    if action == "provider":
        if not args.value:
            from mindvault.config import get as get_config
            print(f"preferred_provider: {get_config('preferred_provider')}")
        else:
            set_config("preferred_provider", args.value)
            print(f"preferred_provider set to: {args.value}")
        return

    print(f"Unknown config action: {action}")


def cmd_status(args) -> None:
    """mindvault status — show current MindVault status."""
    import os

    output_dir = Path("mindvault-out")
    if not output_dir.exists():
        print("No MindVault data found. Run `mindvault` or `/mindvault .` first.")
        return

    graph_path = output_dir / "graph.json"
    wiki_dir = output_dir / "wiki"
    index_path = output_dir / "search_index.json"

    print("=== MindVault Status ===")

    if graph_path.exists():
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes = len(data.get("nodes", []))
        edges = len(data.get("links", []))
        communities = len(data.get("communities", {}))
        mtime = os.path.getmtime(graph_path)
        from datetime import datetime
        last_updated = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  Graph: {nodes} nodes, {edges} edges, {communities} communities")
        print(f"  Last updated: {last_updated}")
    else:
        print("  Graph: not built")

    if wiki_dir.exists():
        wiki_pages = len(list(wiki_dir.glob("*.md")))
        print(f"  Wiki: {wiki_pages} pages")
    else:
        print("  Wiki: not built")

    if index_path.exists():
        idx = json.loads(index_path.read_text(encoding="utf-8"))
        doc_count = idx.get("doc_count", 0)
        print(f"  Search index: {doc_count} documents")
    else:
        print("  Search index: not built")


def cmd_watch(args) -> None:
    """mindvault watch — start file watcher."""
    from mindvault.watch import watch

    source_dir = Path(args.path).resolve()
    output_dir = source_dir / "mindvault-out"

    watch(source_dir, output_dir, debounce=5)


def cmd_update(args) -> None:
    """mindvault update — run incremental pipeline (for git hook)."""
    from mindvault.pipeline import run_incremental

    source_dir = Path(".").resolve()
    output_dir = Path("mindvault-out")

    if not output_dir.exists():
        if not getattr(args, "quiet", False):
            print("No MindVault data found. Skipping update.")
        return

    result = run_incremental(source_dir, output_dir)
    if not getattr(args, "quiet", False):
        print(f"MindVault update: {result}")


def cmd_mark_dirty(args) -> None:
    """mindvault mark-dirty <path> — mark file as needing re-extraction."""
    from mindvault.hooks import mark_dirty

    file_path = Path(args.file_path).resolve()
    output_dir = Path("mindvault-out")
    mark_dirty(file_path, output_dir)


def cmd_flush(args) -> None:
    """mindvault flush — process all dirty files."""
    from mindvault.hooks import flush

    output_dir = Path("mindvault-out")
    result = flush(output_dir)
    print(f"Flush result: {result}")


def cmd_global(args) -> None:
    """mindvault global <root> — global multi-project pipeline."""
    from mindvault.discover import discover_projects

    root = Path(args.root).resolve()
    output_dir = Path.home() / ".mindvault"

    if args.discover:
        # Just list discovered projects
        projects = discover_projects(root)
        print(f"Discovering projects in {root}...")
        print(f"Found {len(projects)} projects:")
        for p in projects:
            print(f"  {p['name']:20s} {p['type']:20s} {p['path']}")
        return

    # Full global build
    from mindvault.global_ import run_global

    print(f"Discovering projects in {root}...")
    result = run_global(root, output_dir)
    print(f"Found {result['projects']} projects.")
    print(f"\nGlobal graph: {result['total_nodes']} nodes, {result['total_edges']} edges, "
          f"{result['cross_project_edges']} cross-project links")
    print(f"Wiki: {output_dir}/wiki/ ({result['wiki_pages']} pages)")
    print(f"Search index: {output_dir}/search_index.json ({result['index_docs']} docs)")

    if args.daemon:
        from mindvault.daemon import install_daemon
        success = install_daemon(root)
        if success:
            print(f"\nDaemon installed: com.mindvault.watcher")
            print(f"  Interval: 300s (5 minutes)")
            print(f"  Log: {output_dir}/daemon.log")
        else:
            print("\nDaemon installation failed.")


def cmd_daemon(args) -> None:
    """mindvault daemon status/stop/log — manage MindVault daemon."""
    from mindvault.daemon import daemon_status, uninstall_daemon

    action = args.action

    if action == "status":
        status = daemon_status()
        print(f"Installed: {status['installed']}")
        print(f"Running: {status['running']}")
        print(f"Mechanism: {status.get('mechanism', 'unknown')}")
        if status.get('config_path'):
            print(f"Config: {status['config_path']}")
        if status.get('last_log_line'):
            print(f"Last log: {status['last_log_line']}")

    elif action == "stop":
        success = uninstall_daemon()
        print(f"Daemon stopped: {success}")

    elif action == "log":
        log_path = Path.home() / ".mindvault" / "daemon.log"
        if log_path.exists():
            content = log_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.strip().split("\n")
            # Show last 20 lines
            for line in lines[-20:]:
                print(line)
        else:
            print("No daemon log found.")

    else:
        print(f"Unknown daemon action: {action}")
        sys.exit(1)


def main() -> None:
    """CLI entry point. Subcommands: install, query, ingest, lint, status, watch, global, daemon."""
    parser = argparse.ArgumentParser(
        prog="mindvault",
        description="MindVault — unified knowledge management: Search + Graph + Wiki",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"mindvault {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # install
    sub_install = subparsers.add_parser("install", help="Install hooks and initialize MindVault in a project")
    sub_install.add_argument("path", nargs="?", default=".", help="Project root path")

    # query
    sub_query = subparsers.add_parser("query", help="Query the knowledge graph")
    sub_query.add_argument("question", help="Question to answer")
    sub_query.add_argument("--mode", default="bfs", choices=["bfs", "dfs", "hybrid"], help="Traversal mode")
    sub_query.add_argument("--budget", type=int, default=2000, help="Token budget")
    sub_query.add_argument("--output-dir", default=None, help="MindVault output directory")
    sub_query.add_argument("--global", dest="use_global", action="store_true", help="Use global ~/.mindvault/ index")

    # ingest
    sub_ingest = subparsers.add_parser("ingest", help="Ingest files into the knowledge graph")
    sub_ingest.add_argument("path", nargs="?", default=".", help="Directory to ingest")
    sub_ingest.add_argument("--incremental", action="store_true", help="Only process changed files")

    # lint
    sub_lint = subparsers.add_parser("lint", help="Check wiki consistency")
    sub_lint.add_argument("path", nargs="?", default=".mindvault", help="Wiki output directory")

    # status
    sub_status = subparsers.add_parser("status", help="Show MindVault status for current project")

    # watch
    sub_watch = subparsers.add_parser("watch", help="Watch for file changes and auto-update")
    sub_watch.add_argument("path", nargs="?", default=".", help="Directory to watch")

    # update (for git hook)
    sub_update = subparsers.add_parser("update", help="Run incremental update (git hook)")
    sub_update.add_argument("--quiet", action="store_true", help="Suppress output")

    # mark-dirty (for Claude Code hook)
    sub_mark_dirty = subparsers.add_parser("mark-dirty", help="Mark a file as dirty")
    sub_mark_dirty.add_argument("file_path", help="File path to mark as dirty")

    # flush (for Claude Code hook)
    sub_flush = subparsers.add_parser("flush", help="Process all dirty files")

    # global
    sub_global = subparsers.add_parser("global", help="Global multi-project pipeline")
    sub_global.add_argument("root", help="Root directory to scan for projects")
    sub_global.add_argument("--discover", action="store_true", help="Just list discovered projects")
    sub_global.add_argument("--daemon", action="store_true", help="Build + install launchd daemon")

    # config
    sub_config = subparsers.add_parser("config", help="Manage MindVault configuration")
    sub_config.add_argument("config_action", choices=["llm", "auto-approve", "provider", "show"], help="Config action")
    sub_config.add_argument("value", nargs="?", default=None, help="Value to set")

    # daemon
    sub_daemon = subparsers.add_parser("daemon", help="Manage MindVault daemon")
    sub_daemon.add_argument("action", choices=["status", "stop", "log"], help="Daemon action")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    commands = {
        "install": cmd_install,
        "query": cmd_query,
        "ingest": cmd_ingest,
        "lint": cmd_lint,
        "status": cmd_status,
        "watch": cmd_watch,
        "update": cmd_update,
        "mark-dirty": cmd_mark_dirty,
        "flush": cmd_flush,
        "config": cmd_config,
        "global": cmd_global,
        "daemon": cmd_daemon,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"mindvault {args.command}: not yet implemented")
        sys.exit(1)


if __name__ == "__main__":
    main()
