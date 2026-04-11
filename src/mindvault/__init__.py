"""MindVault — unified knowledge management: Search + Graph + Wiki."""

__version__ = "0.2.5"


def __getattr__(name: str):
    """Lazy import: only load modules when their symbols are actually accessed."""
    _imports = {
        "search": ("mindvault.search", "search"),
        "build_index": ("mindvault.search", "build_index"),
        "detect": ("mindvault.detect", "detect"),
        "extract_ast": ("mindvault.extract", "extract_ast"),
        "extract_document_structure": ("mindvault.extract", "extract_document_structure"),
        "extract_semantic": ("mindvault.extract", "extract_semantic"),
        "build_graph": ("mindvault.build", "build_graph"),
        "cluster": ("mindvault.cluster", "cluster"),
        "score_cohesion": ("mindvault.cluster", "score_cohesion"),
        "god_nodes": ("mindvault.analyze", "god_nodes"),
        "surprising_connections": ("mindvault.analyze", "surprising_connections"),
        "generate_wiki": ("mindvault.wiki", "generate_wiki"),
        "update_wiki": ("mindvault.wiki", "update_wiki"),
        "compile": ("mindvault.compile", "compile"),
        "run": ("mindvault.pipeline", "run"),
        "run_incremental": ("mindvault.pipeline", "run_incremental"),
        "query": ("mindvault.query", "query"),
        "install_git_hook": ("mindvault.hooks", "install_git_hook"),
        "install_claude_hooks": ("mindvault.hooks", "install_claude_hooks"),
        "mark_dirty": ("mindvault.hooks", "mark_dirty"),
        "flush": ("mindvault.hooks", "flush"),
        "discover_projects": ("mindvault.discover", "discover_projects"),
        "run_global": ("mindvault.global_", "run_global"),
        "run_global_incremental": ("mindvault.global_", "run_global_incremental"),
        "install_daemon": ("mindvault.daemon", "install_daemon"),
        "uninstall_daemon": ("mindvault.daemon", "uninstall_daemon"),
        "daemon_status": ("mindvault.daemon", "daemon_status"),
        "detect_ai_tools": ("mindvault.integrations", "detect_ai_tools"),
        "install_integration": ("mindvault.integrations", "install_integration"),
        "install_all_integrations": ("mindvault.integrations", "install_all_integrations"),
        "load_config": ("mindvault.config", "load_config"),
        "save_config": ("mindvault.config", "save_config"),
        "config_get": ("mindvault.config", "get"),
        "config_set": ("mindvault.config", "set"),
        "detect_llm": ("mindvault.llm", "detect_llm"),
        "call_llm": ("mindvault.llm", "call_llm"),
        "estimate_cost": ("mindvault.llm", "estimate_cost"),
        "confirm_api_usage": ("mindvault.llm", "confirm_api_usage"),
        "ingest": ("mindvault.ingest", "ingest"),
        "ingest_file": ("mindvault.ingest", "ingest_file"),
        "ingest_url": ("mindvault.ingest", "ingest_url"),
    }

    if name in _imports:
        module_path, attr_name = _imports[name]
        import importlib
        module = importlib.import_module(module_path)
        return getattr(module, attr_name)

    raise AttributeError(f"module 'mindvault' has no attribute {name!r}")


__all__ = [
    "__version__",
    "search",
    "build_index",
    "detect",
    "extract_ast",
    "extract_document_structure",
    "extract_semantic",
    "build_graph",
    "cluster",
    "score_cohesion",
    "god_nodes",
    "surprising_connections",
    "generate_wiki",
    "update_wiki",
    "compile",
    "run",
    "run_incremental",
    "query",
    "install_git_hook",
    "install_claude_hooks",
    "mark_dirty",
    "flush",
    "discover_projects",
    "run_global",
    "run_global_incremental",
    "install_daemon",
    "uninstall_daemon",
    "daemon_status",
    "detect_ai_tools",
    "install_integration",
    "install_all_integrations",
    "load_config",
    "save_config",
    "config_get",
    "config_set",
    "detect_llm",
    "call_llm",
    "estimate_cost",
    "confirm_api_usage",
    "ingest",
    "ingest_file",
    "ingest_url",
]
