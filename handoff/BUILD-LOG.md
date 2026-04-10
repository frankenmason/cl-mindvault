# BUILD-LOG — MindVault

## Project Summary
MindVault — 토큰 절약 + 세션 연속성을 위한 3-Layer 지식 관리 도구.
PyPI 독립 패키지. `pip install mindvault && mindvault install`

## Steps

### Step 1 — Project Skeleton + Module Interfaces ✅
- **Builder**: Bob
- **Date**: 2026-04-09
- **Status**: COMPLETE
- **Files**: 22 files created (pyproject.toml, README.md, 18 Python modules, SKILL.md, REVIEW-REQUEST.md)
- **Verification**:
  - `pip install -e .` — PASS
  - `mindvault --version` → `mindvault 0.1.0` — PASS
  - All module imports — PASS
  - SKILL.md exists — PASS
- **Notes**: cli.py has working argparse (not stub). All other modules are stubs with NotImplementedError.

### Step 2 — Graph Layer Implementation ✅
- **Builder**: Bob
- **Date**: 2026-04-09
- **Status**: COMPLETE
- **Files modified**: 6 (detect.py, cache.py, extract.py, build.py, cluster.py, analyze.py)
- **Verification** (all 5 tests PASS):
  - Test 1: `detect` — 24 files, 3636 words, 19 code files — PASS
  - Test 2: `extract_ast` — 66 nodes, 281 edges — PASS
  - Test 3: `build_graph` — 66 nodes, 79 edges (dangling edges filtered) — PASS
  - Test 4: `cluster + analyze` — 13 communities, 5 god nodes, 5 surprises — PASS
  - Test 5: `cache` — dirty detection + update — PASS
- **Key decisions**:
  - `nx.Graph` → `nx.DiGraph` (as specified)
  - tree-sitter 0.25.2 API: `Parser(lang)` constructor, no `.set_language()`
  - `greedy_modularity_communities` on undirected copy for clustering
  - Node IDs: `{filestem}_{entityname}` with sanitization (lowercase, special→underscore)
  - Call edges extracted recursively from function bodies, cross-file resolution deferred
  - `extract_semantic` remains NotImplementedError stub

### Step 3 — Wiki Layer + Output Generation ✅
- **Builder**: Bob
- **Date**: 2026-04-09
- **Status**: COMPLETE
- **Files modified**: 5 (wiki.py, compile.py, report.py, export.py, lint.py)
- **Verification** (all 4 tests PASS):
  - Test 1: `compile` — 70 nodes, 95 edges, 11 communities, 12 wiki pages, 5637 words — PASS
  - Test 2: output files — graph.json, GRAPH_REPORT.md, graph.html, wiki/INDEX.md all exist, 12 wiki pages — PASS
  - Test 3: lint — 12 pages, 193 broken wikilinks (node-level refs to non-existent pages, expected), 0 orphans, 0 ambiguous edges — PASS
  - Test 4: report sections — Overview, God Nodes, Communities all present — PASS
- **Key decisions**:
  - Community labels auto-generated from top-2 nodes by degree (no LLM)
  - Wiki context uses template: "이 커뮤니티는 {top}를 중심으로 {relation} 관계로 연결되어 있다."
  - vis.js HTML: CDN from unpkg, community colors, degree-based node sizing, search, community filter checkboxes
  - `node_link_data(G, edges="links")` to suppress NetworkX 3.6 FutureWarning
  - Broken wikilinks are node-level `[[slug]]` refs pointing to individual nodes (not community pages). This is expected since only community-level and INDEX pages are generated.
  - `extract_semantic` remains NotImplementedError stub (as specified)

### Step 4 — Search Layer Implementation ✅
- **Builder**: Bob
- **Date**: 2026-04-09
- **Status**: COMPLETE
- **Files modified**: 2 (index.py, search.py)
- **Verification** (all 5 tests PASS):
  - Test 1: `index_markdown` — 12 documents indexed — PASS
  - Test 2: `search("detect file")` — 1 result, score 2.32 — PASS
  - Test 3: `search("xyznonexistent")` — 0 results (empty list) — PASS
  - Test 4: `update_index` — 0 updated (no changes) — PASS
  - Test 5: `build_index` wrapper — delegates to `index_markdown` correctly — PASS
- **Key decisions**:
  - Pure Python BM25 (Okapi), no external search libraries
  - Tokenization: lowercase + whitespace split + remove <=2 char tokens (shared between index and search)
  - IDF: `log(N / (1 + df))` as specified
  - BM25 params: k1=1.5, b=0.75 (standard)
  - Snippet: +-30 chars around first query token match, fallback to first 100 chars
  - `update_index` signature changed from `(changed_files, index_path)` to `(docs_dir, index_path)` per brief spec — it scans dir and uses SHA256 hash to detect changes
  - `search` signature simplified from `(query, index_path, mode="hybrid")` to `(query, index_path, top_k=5)` — vector/hybrid mode deferred
  - Index JSON stores tokens per doc for BM25 tf computation at search time

### Step 5 — Integration Layer + CLI ✅
- **Builder**: Bob
- **Date**: 2026-04-10
- **Status**: COMPLETE
- **Files modified**: 5 (pipeline.py, query.py, hooks.py, watch.py, cli.py)
- **Verification** (all 6 tests PASS):
  - Test 1: `pipeline.run` — 91 nodes, 17 index_docs — PASS
  - Test 2: `query("detect file")` — 3 search results, 4 graph nodes, tokens_used=1991 (<2000) — PASS
  - Test 3: `mindvault status` — 91 nodes, 146 edges, 10 communities, 17 wiki pages, 17 indexed docs — PASS
  - Test 4: `mindvault query "detect file"` — 3-layer formatted output — PASS
  - Test 5: `mindvault lint` — 17 pages, 358 broken wikilinks (node-level refs), 0 ambiguous edges — PASS
  - Test 6: `mark_dirty + flush` — mark 1 file, flush runs incremental, returns result — PASS
- **Key decisions**:
  - `pipeline.run`: calls `compile()` then `index_markdown()` on wiki dir
  - `pipeline.run_incremental`: uses `cache.get_dirty_files` for dirty detection, merges into existing graph.json, re-clusters, re-generates wiki + index
  - `query.py`: 3-layer pipeline (BM25 → graph BFS/DFS → wiki read). Budget enforcement reserves tokens for graph edges before allocating to wiki content
  - `hooks.py`: git hook appends to existing post-commit (preserves content). Claude hooks are opt-in only (not auto-activated by install). Dirty list stored as JSON array in `.mindvault_dirty.json`
  - `watch.py`: mtime polling with configurable debounce. Code changes trigger `run_incremental`, doc changes only `mark_dirty`
  - `cli.py`: extended existing argparse with 3 new subcommands (update, mark-dirty, flush). All original subcommands now have real implementations

### Step 6 — SKILL.md Completion + Deployment Preparation ✅
- **Builder**: Bob
- **Date**: 2026-04-10
- **Status**: COMPLETE
- **Files created/modified**: 3 (skill/SKILL.md rewritten, README.md rewritten, .gitignore created)
- **Verification** (all 7 tests PASS):
  - Test 1: `mindvault ingest src` — 91 nodes, 146 edges, 10 communities, 11 wiki pages, 11 indexed docs — PASS
  - Test 2: `mindvault query "how does the search layer work"` — 3-layer output, 1992 tokens — PASS
  - Test 3: `mindvault status` — 91 nodes, 146 edges, 10 communities, 11 wiki pages, 11 docs — PASS
  - Test 4: `mindvault lint` — 11 pages, 288 broken wikilinks (node-level, expected), 0 orphans, 0 ambiguous — PASS
  - Test 5: `mindvault install` — skill copied, CLAUDE.md registered — PASS
  - Test 6: Output files — graph.json, graph.html, GRAPH_REPORT.md, wiki/INDEX.md, search_index.json, 10 community pages — PASS
  - Test 7: `git init` + first commit `57e6c05` — 32 files, .gitignore excludes mindvault-out/ — PASS
- **Key decisions**:
  - SKILL.md follows Graphify pattern: YAML frontmatter, step-by-step bash blocks with Python one-liners, interpreter detection via `.mindvault_python` file
  - SKILL.md covers all subcommands: full pipeline, query, lint, status, ingest, install
  - README.md includes token savings table, 3-layer diagram, full commands table
  - Git commit does NOT push (user creates GitHub repo first)

### Step 7 — Global Mode + Daemon ✅
- **Builder**: Bob
- **Date**: 2026-04-09
- **Status**: COMPLETE
- **Files created**: 3 (discover.py, global_.py, daemon.py)
- **Files modified**: 3 (cli.py, __init__.py)
- **Verification** (all 5 tests PASS):
  - Test 1: `discover_projects` — 9 projects found (base-mcp, campusflow, doc-scanner, mindvault, oneshot, seed, taxi-ledger, youtube-longform, youtube-pipeline) — PASS
  - Test 2: `run_global` — 556 nodes, 787 edges, 184 cross-project edges, 143 wiki pages, 143 index docs — PASS
  - Test 3: `mindvault query "TTS 음성" --global` — matched 19 TTS nodes across youtube-longform/youtube-pipeline, cross-project shares_name_with edges shown — PASS
  - Test 4: `mindvault global ... --discover` — 9 projects listed with types — PASS
  - Test 5: `install_daemon` + `daemon_status` + `uninstall_daemon` — plist created/loaded/unloaded — PASS
- **Key decisions**:
  - BFS discovery skips SKIP_DIRS from detect.py, skips nested projects (once found, don't descend)
  - package.json type inference: checks deps for next/react-native/expo/remotion/react
  - Cross-project edges: nodes with same label across different projects get `shares_name_with` INFERRED edges
  - Node IDs prefixed with `{project_name}/` for global uniqueness
  - Daemon uses macOS launchd plist at ~/Library/LaunchAgents/com.mindvault.watcher.plist
  - `--global` flag on query switches output_dir to ~/.mindvault/
  - `global_.py` naming (not `global.py`) because `global` is Python reserved word

### Step 8 — Multi-AI Tool Integration ✅
- **Builder**: Bob
- **Date**: 2026-04-09
- **Status**: COMPLETE
- **Files created**: 1 (integrations.py)
- **Files modified**: 2 (cli.py, __init__.py)
- **Verification** (all 4 tests PASS):
  - Test 1: `detect_ai_tools` on mindvault project — Claude Code detected via CLAUDE.md — PASS
  - Test 2: `detect_ai_tools` on taxi-ledger — no AI tool files found (no CLAUDE.md in that dir), prints PASS — PASS
  - Test 3: `install_all_integrations` in temp dir — 3 tools detected (Claude Code, Cursor, GitHub Copilot), all installed, second run all `already_exists` — PASS
  - Test 4: `mindvault install` CLI — detects Claude Code, shows already configured, skill registered, git hook installed — PASS
- **Key decisions**:
  - `AI_TOOLS` config list with 7 tools (Claude Code, Cursor, GitHub Copilot, Windsurf, Gemini Code Assist, Cline, Aider)
  - Claude Code gets `## MindVault` section (append_section type), all others get `# MindVault Knowledge Base` block (create_or_append type)
  - Idempotent: checks for "MindVault" string in existing file content before appending
  - `cmd_install` now prints detection results for all 7 tools with checkmarks, then installation results, then skill registration and git hook
  - Parent directories created automatically (.github/, .gemini/) when needed
  - Only detected tools get rules files created — no spurious file creation

### Step 9 — Semantic Extraction (LLM Auto-Detect + Consent) ✅
- **Builder**: Bob
- **Date**: 2026-04-09
- **Status**: COMPLETE
- **Files created**: 3 (config.py, llm.py, ingest.py)
- **Files modified**: 4 (extract.py, compile.py, cli.py, __init__.py)
- **Verification** (all 6 tests PASS):
  - Test 1: `detect_llm` — Gemma detected at localhost:8080, model `mlx-community/gemma-4-e4b-it-4bit` — PASS
  - Test 2: `call_llm` — Local Gemma returns JSON extraction (3 concepts) — PASS
  - Test 3: `ingest(README.md)` — 13 nodes, 14 edges extracted from README — PASS
  - Test 4: `extract_semantic` — 10 nodes, 10 edges from doc files — PASS
  - Test 5: `config` — load/save/get/set all work, persists to `~/.mindvault/config.json` — PASS
  - Test 6: Full pipeline with semantic — 271 nodes, 373 edges, 40 wiki pages, 52 index docs — PASS
- **Key decisions**:
  - `detect_llm` auto-discovers Gemma model name from `/v1/models` endpoint (handles MLX server's full model ID like `mlx-community/gemma-4-e4b-it-4bit`)
  - `call_llm` uses `max_tokens: 4000` for local models to avoid `finish_reason: length` truncation
  - Gemma 4 returns `reasoning` field alongside `content` — code correctly accesses `content` only
  - `compile.py` now calls `extract_ast` + `extract_semantic` and merges via `_merge_extractions`
  - JSON parse failures in LLM response → warning to stderr, file skipped, pipeline continues
  - API consent: local LLM = no consent needed; API keys = `confirm_api_usage()` with cost estimate
  - Config at `~/.mindvault/config.json` with keys: `llm_endpoint`, `auto_approve_api`, `max_tokens_per_file`, `preferred_provider`
  - `cli.py` gains `config` subcommand (llm, auto-approve, provider, show) and `cmd_ingest` handles URLs
  - `ingest.py` supports file/URL/directory ingestion with HTML stripping for URLs
  - All uses `urllib.request` only — zero `requests` dependency

## Known Gaps

- Cross-file call/import resolution: imports create edges to `{module}_module` IDs which may or may not exist as nodes; dangling ones are filtered by `build_graph`
- Broken wikilinks: node-level `[[slug]]` references in community pages point to slugs that don't have dedicated wiki pages (193 in self-compile). Could add per-node pages or switch to anchor links.
- `update_wiki` is minimal (returns 0) — needs community tracking for true incremental updates
- Image vision analysis: `.png`/`.jpg`/`.webp` files skipped during ingestion (Known Gap per spec)
- PDF extraction: requires `pdftotext` CLI tool; if missing, PDF files are skipped (not an error)
- YouTube URL ingestion: `yt-dlp` subtitle extraction not yet implemented (deferred)
