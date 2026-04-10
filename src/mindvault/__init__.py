"""MindVault — unified knowledge management: Search + Graph + Wiki."""

__version__ = "0.2.2"

from mindvault.search import search, build_index
from mindvault.detect import detect
from mindvault.extract import extract_ast, extract_document_structure, extract_semantic
from mindvault.build import build_graph
from mindvault.cluster import cluster, score_cohesion
from mindvault.analyze import god_nodes, surprising_connections
from mindvault.wiki import generate_wiki, update_wiki
from mindvault.compile import compile
from mindvault.pipeline import run, run_incremental
from mindvault.query import query
from mindvault.hooks import install_git_hook, install_claude_hooks, mark_dirty, flush
from mindvault.discover import discover_projects
from mindvault.global_ import run_global, run_global_incremental
from mindvault.daemon import install_daemon, uninstall_daemon, daemon_status
from mindvault.integrations import detect_ai_tools, install_integration, install_all_integrations
from mindvault.config import load_config, save_config
from mindvault.config import get as config_get
from mindvault.config import set as config_set
from mindvault.llm import detect_llm, call_llm, estimate_cost, confirm_api_usage
from mindvault.ingest import ingest, ingest_file, ingest_url

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
