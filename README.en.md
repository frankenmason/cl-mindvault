<p align="center">
  <h1 align="center">MindVault</h1>
  <p align="center">Long-term memory for AI coding tools — auto-converts codebases into knowledge graph + wiki + search index</p>
</p>

<p align="center">
  <a href="https://pypi.org/project/mindvault-ai/"><img src="https://img.shields.io/pypi/v/mindvault-ai?color=blue" alt="PyPI"></a>
  <img src="https://img.shields.io/pypi/pyversions/mindvault-ai" alt="Python 3.10+">
  <img src="https://img.shields.io/github/license/etinpres/mindvault" alt="MIT License">
</p>

**English** | [한국어](README.md)

---

## Why MindVault?

AI coding tools (Claude Code, Cursor, Copilot, etc.) **forget all context once a session ends.** Every time you start a new session, you have to spend time repeatedly explaining, "This project has this structure, and this function works like this..." This is a **waste of time and tokens.**

Previously, this problem was addressed by three separate tools:

| Existing Tool | Role | Limitations |
|-----------|------|------|
| **qmd** | Local search with BM25 | Search only, cannot grasp relationships |
| **graphify** | Knowledge graph generation | No search/wiki |
| **llm-wiki-compiler** | Wiki compilation | No graph/search |

MindVault integrates the advantages of these three into **one installation line and zero configuration.** It is inspired by [Andrej Karpathy's LLM Wiki Pattern](https://x.com/karpathy).

---

## 3-Layer Architecture

```
                    Query: "How does authentication work?"
                              |
                    +---------v---------+
                    |  1. Search Layer  |  Local Search with BM25
                    |  (Token Cost: 0)   |  Supports Korean/English/CJK
                    +---------+---------+
                              |
                    +---------v---------+
                    |  2. Graph Layer   |  Knowledge Graph Traversal
                    |  (Token ~100)      |  BFS/DFS Neighbor Nodes
                    +---------+---------+
                              |
                    +---------v---------+
                    |  3. Wiki Layer    |  Reading Community Wiki
                    |  (Token ~800)      |  Why/How Context
                    +---------+---------+
                              |
                        Answer generation
                    (Total ~900 tokens per query)
```

| Layer | Role | Token Cost | Technology |
|-------|------|-----------|------|
| **Search** | Discover relevant wiki pages via keyword matching | 0 (Local operation) | BM25 Inverted Index |
| **Graph** | Explore relationships/neighbors of matched nodes | ~100 | NetworkX BFS/DFS |
| **Wiki** | Extract context from community pages | ~800 | Markdown Wiki |
| **Total** | | **~900** | **60x+ reduction vs. reading source directly** |

---

## Installation

```bash
pip install mindvault-ai
mindvault install
```

What `mindvault install` performs automatically:
- Detects the currently used AI tool (supports 10)
- Creates integrated configuration files for each tool
- Installs Git post-commit hook (auto-updates on commit)
- Registers Claude Code `/mindvault` Skill
- **Installs auto-context hook** — automatically injects MindVault context into every query (system-level)

### Requirements

- **Python 3.10+**
- **Python dependencies (auto-installed via pip)**
  - `networkx` — knowledge graph engine
  - `tree-sitter` + 13 language parsers — AST-based code structure analysis
  - `python-docx`, `openpyxl`, `python-pptx` — Office document (.docx / .xlsx / .pptx) extraction (v0.2.7+)
- **Optional system binaries**
  - `pdftotext` — required only for PDF extraction (macOS: `brew install poppler`, Ubuntu: `apt install poppler-utils`, Windows: [Xpdf tools](https://www.xpdfreader.com/download.html))
- AST-based code structure analysis works without an LLM
- Local LLM or API key required for semantic extraction (see [LLM Setup](#llm-configuration) below)

---

## Quick Start

### 1. Install & Initialize

```bash
pip install mindvault-ai
cd ~/your-project
mindvault install .    # hooks + daemon auto-registered (checks every 5 min)
```

Two ways to build the initial knowledge base:

```bash
# Option A: Build a single project
mindvault ingest .

# Option B: Build all projects at once
mindvault global ~/projects
```

| Command | Scope | Use case |
|---------|-------|----------|
| `mindvault ingest .` | Current folder only | Quick build for one project |
| `mindvault global <root>` | All sub-projects | Unified build with cross-project relationships |

> After the initial build, the daemon auto-detects changes every 5 minutes.
> Skip daemon with `mindvault install . --no-daemon`

#### Indexing Files Outside the Root Folder

You can manually ingest files/folders outside the root path with `mindvault ingest`:

```bash
# Example: index config scripts in your home directory
mindvault ingest ~/.config/my-tool/

# Example: index docs from another location
mindvault ingest /opt/docs/api-reference/
```

> **Note:** Paths outside the root folder are not monitored by the daemon. If those files change, you need to run `mindvault ingest` again manually.

#### Supported Document Formats

| Format | Status | Notes |
|--------|--------|-------|
| `.md`, `.txt`, `.rst` | ✅ Built-in | — |
| `.pdf` | ✅ Built-in | Requires system `pdftotext` |
| `.docx`, `.xlsx`, `.pptx` | ✅ Built-in (v0.2.7+) | Word / Excel / PowerPoint auto-detected |

No extra install is needed — just run `mindvault ingest /path/to/docs` and all the above formats are extracted automatically.

### 2. Use

```bash
# 3-layer integrated query
mindvault query "How does authentication work?"

# DFS mode (deeply tracing a specific call chain)
mindvault query "What is the full call chain of this function?" --dfs

# Check current status
mindvault status
```

### Claude Code Skill Usage

```
/mindvault .
/mindvault query "How does the pipeline work?"
```

---

## How It Works

```
Source File / URL / PDF / Documents
        |
        v
  [1. Detect]     -- Scans code/document/PDF/image files, auto-detects projects via 14 marker files
        |
        v
  [2. Extract]    -- Code: tree-sitter AST (functions, classes, imports)
        |             Documents: structure extraction (header hierarchy, links, code blocks) ← No LLM needed
        |             PDF: section structure extraction
        v
  [3. Semantic]   -- LLM analyzes meaning/intent (optional, applies to both code and docs)
        |
        v
  [4. Build]      -- Constructs NetworkX DiGraph, filters dangling edges
        |
        v
  [5. Cluster]    -- Detects communities using greedy modularity
        |
        v
  [6. Wiki]       -- Automatically generates Markdown wiki per community (Obsidian [[wikilinks]] compatible)
        |
        v
  [7. Index]      -- Builds BM25 inverted index (Korean/English/CJK)
        |
        v
    mindvault-out/
```

> **Note**: Step 2 (Extract) automatically branches by input type. Code files go through AST analysis, documents/PDFs go through structure extraction. Both paths require zero LLM calls and zero tokens. Step 3 (Semantic) only runs when an LLM is available and applies to both code and documents.

### Output Directory Structure

```
mindvault-out/
├── graph.json           # Original graph data (nodes + edges)
├── graph.html           # vis.js interactive visualization (open in browser)
├── GRAPH_REPORT.md      # Analysis report (God Nodes, Surprising Connections)
├── wiki/
│   ├── INDEX.md         # Wiki entry point (list of all communities)
│   ├── *.md             # Wiki pages per community
│   ├── _concepts.json   # Concept index (for cross-references)
│   ├── ingested/        # Knowledge pages from external sources
│   └── queries/         # Saved query/answer records
├── search_index.json    # BM25 search index
└── sources/             # Collected external materials (URL, PDF, etc.)
```

---

## CLI Reference

### Core Commands

| Command | Description |
|--------|------|
| `mindvault install` | AI tool detection + integrated setup + Git hook + Skill registration |
| `mindvault ingest <path/url>` | Collects files/URLs/folders → auto-updates graph + wiki + index |
| `mindvault query "<question>"` | 3-layer integrated query (search → graph → wiki) |
| `mindvault status` | Displays current graph/wiki/index status |

### Query Options

| Command | Description |
|--------|------|
| `mindvault query "<question>"` | Default BFS mode (wide search) |
| `mindvault query "<question>" --dfs` | DFS mode (deep call chain tracing) |
| `mindvault query "<question>" --global` | Cross-project search from the global index |

### Update & Watch

| Command | Description |
|--------|------|
| `mindvault update` | Incremental update (automatically called by git hook) |
| `mindvault watch` | Real-time file change monitoring (polling-based) |
| `mindvault mark-dirty <path>` | Marks a specific file as dirty (for re-extraction) |
| `mindvault flush` | Processes all dirty files |

### Global Mode

| Command | Description |
|--------|------|
| `mindvault global <root>` | Builds all sub-projects into one |
| `mindvault global <root> --discover` | Outputs project list only (no build) |
| `mindvault global <root> --daemon` | Build + daemon registration (not needed if already registered via install) |

### Daemon Management

> The daemon is automatically registered during `mindvault install`. Use these commands to check status or manage it.

| Command | Description |
|--------|------|
| `mindvault daemon status` | Checks daemon status |
| `mindvault daemon stop` | Stops the daemon |
| `mindvault daemon log` | Checks daemon logs |

### Configuration

| Command | Description |
|--------|------|
| `mindvault config llm <url>` | Sets a generic OpenAI-compatible LLM endpoint |
| `mindvault config ollama-host <url>` | Override Ollama host (e.g. WSL → Windows) |
| `mindvault config llm-model <name>` | Force a specific model name (overrides auto-detection) |
| `mindvault config auto-approve true/false` | Sets auto-approval for API calls |
| `mindvault config show` | Displays current configuration |
| `mindvault lint` | Checks wiki consistency + graph health |
| `mindvault --version` | Checks version |

---

## Token Savings Benchmark

### Single Project

| Scenario | Original Read | MindVault Query | Savings |
|----------|---------------|----------------|-----------|
| Small (20 files) | ~15,000 tokens | ~900 tokens | **17x** |
| Medium (100 files) | ~60,000 tokens | ~900 tokens | **67x** |
| Large (500 files) | ~300,000 tokens | ~900 tokens | **333x** |

### Actual Measurement (MindVault Source, 24 files)

| Metric | Value |
|------|------|
| Nodes | 271 |
| Edges | 373 |
| Wiki Pages | 40 |
| Tokens per Query | ~900 |

### Global Mode (9 Projects Integrated)

| Metric | Value |
|------|------|
| Nodes | 572 |
| Edges | 670 |
| Cross-Project Links | 33 |

The query token budget can be adjusted with the `--budget` option (Default: 2000 tokens).

---

## Supported Languages

13 languages supporting tree-sitter based AST extraction:

| Language | Language | Language |
|------|------|------|
| Python | TypeScript | JavaScript |
| Go | Rust | Java |
| Swift | Kotlin | C |
| C++ | Ruby | C# |
| Scala | PHP | Lua |

---

## AI Tool Integration

It automatically generates configuration files matching the detected tool upon running `mindvault install`.

| AI Tool | Generated Config File |
|---------|-------------------|
| **Claude Code** | `CLAUDE.md` + `SKILL.md` |
| **Cursor** | `.cursorrules` |
| **GitHub Copilot** | `.github/copilot-instructions.md` |
| **Windsurf** | `.windsurfrules` |
| **Gemini Code Assist** | `.gemini/styleguide.md` |
| **Cline** | `.clinerules` |
| **Aider** | `CONVENTIONS.md` |
| **AGENTS.md Standard** (OpenAI Codex CLI, Google Antigravity, ...) | `AGENTS.md` |
| **Google Gemini CLI** | `GEMINI.md` |
| **Qwen Code** | `QWEN.md` |

---

## Viewing Output in Obsidian (Optional)

> MindVault is a CLI tool built for **developers using AI coding agents** (Claude Code, Codex, Cursor, etc.). It works fully standalone — Obsidian is not required. The following section only applies if you already use Obsidian or want a nicer UI to browse the generated wiki pages.

**There is no Obsidian plugin.** MindVault just emits plain markdown; Obsidian can open that folder as a vault and give you backlinks / graph view / search for free. No additional dependencies.

### Pattern A: Open MindVault output as an Obsidian vault (most common)

Index your codebase first:

```bash
mindvault ingest .
```

This creates per-community markdown wiki pages under `mindvault-out/wiki/`. **Open that folder as an Obsidian vault** and everything just works:

- ✅ Obsidian's graph view visualizes the MindVault knowledge graph
- ✅ `[[link]]` bidirectional navigation
- ✅ Search / tags / backlinks / outline panels all apply

You get Andrej Karpathy's LLM Wiki pattern **auto-generated and served through Obsidian's UI**, with zero manual wiki maintenance.

### Pattern B: Index an existing Obsidian vault (requires Python + an AI coding agent)

> This pattern is **not for plain Obsidian users**. It requires Python 3.10+, `pip install mindvault-ai`, and either Claude Code or a local LLM if you want semantic extraction. It's aimed at developers who already use AI coding agents and want a knowledge graph over their existing vault.

If you already have an Obsidian vault, point MindVault at it:

```bash
mindvault ingest ~/my-obsidian-vault
```

MindVault automatically handles:

- `.md` headers → graph nodes
- `[[wikilinks]]` → graph edges (your vault's existing link structure is preserved)
- BM25 search index built over the whole vault

Then run 3-layer queries directly against your existing notes:

```bash
mindvault query "key decisions for Project R"
```

### Pattern C: Unified code + notes search

Index both a code project (Pattern A) and an Obsidian vault (Pattern B) — they merge into one knowledge graph:

```bash
mindvault global ~/projects           # all your code
mindvault ingest ~/my-obsidian-vault  # your notes
mindvault query "rationale behind the auth module" --global
```

→ Code structure (Graph Layer) plus the design decisions from your Obsidian notes (Wiki Layer) flow into a single answer.

> **Tip**: Use Obsidian's "Folder as vault" feature to open `mindvault-out/wiki/` directly — no copying or symlinks needed.

### Native Obsidian features (v0.3.0+)

Starting with v0.3.0, ingesting an Obsidian vault automatically handles:

| Feature | Description |
|---------|-------------|
| **YAML frontmatter parsing** | `title`, `tags`, `aliases`, etc. inside `---` blocks are attached to the first header (or a synthetic file node) as metadata |
| **Inline `#tags`** | `#project`, `#auth`, `#nested/tag` in prose are collected per note (numeric / hex-color strings are skipped) |
| **Recursive directory walk** | `mindvault ingest ~/my-vault` now traverses subfolders |
| **Auto-excluded dirs** | `.obsidian/`, `.trash/`, `.stfolder/`, `.stversions/` are skipped by default |

Example — a real Obsidian note with frontmatter and tags:

```markdown
---
title: Auth Rewrite Plan
tags: [project, auth, 2026-q2]
status: in-progress
---

# Auth Rewrite Plan

#architecture decisions live in [[ADR-007]]. Ship after #security review.
```

→ The resulting graph node carries `metadata: {title, tags, status}`, inherits `#architecture` and `#security` as tags, and the `[[ADR-007]]` wikilink becomes a graph edge.

---

## LLM Configuration

MindVault utilizes an LLM for semantic extraction (analyzing code intent/purpose). **AST-based structural analysis functions correctly even without an LLM.**

### Auto-Detection Order

It prioritizes local LLMs, and if none are found, it uses subscribed tokens or an API:

| Priority | LLM | Method | Cost | Consent |
|----------|-----|------|------|-----------|
| 1 | **Gemma (Local)** | `localhost:8080` | Free | Not Required |
| 2 | **Ollama (Local)** | `localhost:11434` | Free | Not Required |
| 3 | **Claude Code Skill** | Run with `/mindvault` | Subscription Tokens | Not Required |
| 4 | **Anthropic Claude Haiku** | API Key | Paid | **Required** |
| 5 | **OpenAI GPT-4o-mini** | API Key | Paid | **Required** |
| 6 | **No LLM** | — | Free | — |

- **Local LLM**: Called immediately without consent (Free).
- **Claude Code Subscriber**: Running with the `/mindvault` skill allows Claude to perform the extraction without needing a separate API key, using only subscription tokens.
- **API Key Usage**: Called only after displaying estimated costs and obtaining user consent.
- **No LLM**: AST-based code structure analysis functions normally. Only semantic extraction (document meaning analysis) is skipped.

> **Most users are Claude Code/Cursor/Copilot subscribers.** Running with the `/mindvault` skill enables semantic extraction without additional setup.

```bash
# Generic OpenAI-compatible LLM endpoint
mindvault config llm http://localhost:8080

# Override Ollama host (e.g. WSL reaching Windows-side Ollama)
mindvault config ollama-host http://172.28.112.1:11434
# The $OLLAMA_HOST environment variable is honored as well.

# Force a specific model name (overrides auto-detection)
mindvault config llm-model gemma3:e4b
mindvault config llm-model qwen3:4b

# Auto-approve API usage (no prompting)
mindvault config auto-approve true

# Check current configuration
mindvault config show
```

> **v0.2.9+**: Ollama now auto-discovers installed models via `/api/tags` and prefers gemma3, gemma, qwen3, qwen in that order. For WSL → Windows setups, point MindVault at the Windows host IP with `ollama-host` or `$OLLAMA_HOST`.

---

## Project Auto-Discovery

When automatically discovering sub-projects in Global Mode (`mindvault global`), it recognizes a project if any of the following 14 marker files are present:

| Marker File | Ecosystem | Marker File | Ecosystem |
|-----------|--------|-----------|--------|
| `package.json` | Node.js | `Cargo.toml` | Rust |
| `pyproject.toml` | Python | `go.mod` | Go |
| `setup.py` | Python | `pubspec.yaml` | Flutter/Dart |
| `build.gradle` | Java/Kotlin | `build.gradle.kts` | Kotlin |
| `Podfile` | iOS/macOS | `Gemfile` | Ruby |
| `composer.json` | PHP | `CMakeLists.txt` | C/C++ |
| `Makefile` | Generic | `CLAUDE.md` | Claude Code |

---

## Cross-Platform Daemon

The daemon is automatically registered during `mindvault install`. You can also register it with `mindvault global <root> --daemon`. It uses the OS's native service manager to auto-detect changes every 5 minutes.

| OS | Service Manager | Notes |
|----|-------------|------|
| **macOS** | launchd (LaunchAgent) | Starts automatically upon login |
| **Windows** | Task Scheduler | Logon Trigger |
| **Linux** | systemd user service | `--user` mode |

```bash
# Check daemon status
mindvault daemon status

# Stop daemon
mindvault daemon stop

# Check daemon logs
mindvault daemon log
```

---

## Cache & Incremental Updates

MindVault uses a **SHA256 hash-based incremental cache**. It does not reprocess files that have not changed.

- Git post-commit hook automatically runs `mindvault update` upon commit.
- Only changed files are re-extracted → Graph/Wiki/Index updated.
- Real-time monitoring is also possible with `mindvault watch` (polling-based).

---

## Auto-Context Hook (The Key to Session Continuity)

The most important feature of MindVault. When you run `mindvault install`, a **system-level hook** is installed that makes the AI **automatically** reference MindVault on every question.

```
User: "How does the Telegram bot handle comments on videos?"
  ↓ (System auto-executes — not the AI's choice)
  mindvault query "How does the Telegram bot handle comments?" --global
  ↓
  <mindvault-context> search results + graph + wiki </mindvault-context>
  ↓
AI: Already has context, gives accurate answer
```

- Short messages under 10 chars are auto-skipped
- 5-second timeout prevents response delay
- Slash commands (`/`) are also skipped

Without this hook, the AI must "voluntarily" follow CLAUDE.md instructions — which it sometimes ignores. The hook is **system-enforced**, so the AI cannot forget.

---

## Memory Integration

During global builds (`mindvault global`), Claude Code's `~/.claude/projects/*/memory/*.md` files are automatically included in the search index. Code analysis results and project memories are merged into a **single unified search index**.

```
Search: "telegram bot"
  → Code analysis (tg_notify.sh related nodes)
  → MEMORY.md (custom bot decision records)
  → Wiki pages (TTS pipeline relationships)
  = All sources unified
```

---

## Incremental Knowledge Accumulation (Karpathy LLM Wiki Pattern)

Inspired by [Andrej Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), MindVault's wiki **grows richer over time.**

### How It Differs from Existing Tools

| | Traditional | MindVault |
|---|---|---|
| **Wiki generation** | Full rebuild every time | Updates only changed parts, preserves existing |
| **User notes** | Lost on rebuild | `<!-- user-notes -->` section permanently preserved |
| **External sources** | Managed separately | Auto-classified and merged into existing communities |
| **Query history** | Lost | Accumulated in `wiki/queries/`, searchable |
| **Contradiction detection** | None | 3-level auto-detection (see below) |

### How Knowledge Accumulates

```
Day 1: mindvault ingest . -> code analysis -> 30 wiki pages created
        |
Day 2: Code change -> daemon auto-detects -> only 3 pages updated
        |
Day 3: mindvault ingest paper.pdf -> auto-merged into "auth" community
        |
Day 4: mindvault query "auth flow" --save -> answer saved to wiki/queries/
        |
  ...wiki grows richer. User notes preserved.
```

### Cross-References

All wiki pages are connected via the `_concepts.json` index. When new material is added, automatic backlinks are created to related existing pages. Use Obsidian's Graph View to visualize the entire knowledge structure.

### Contradiction Detection

When the same concept appears across multiple wiki pages, `mindvault lint` automatically detects contradictions. It works in 3 levels depending on your environment:

| Environment | How contradictions are judged | Accuracy |
|---|---|---|
| **Local LLM available** (Gemma/Ollama) | LLM judges whether two descriptions contradict | High |
| **Running via subscription AI** (`/mindvault lint`) | Claude/Cursor judges directly | High |
| **Neither available** | String comparison flags suspicious differences | Basic |

- Local LLM is free, so no consent is needed
- API keys are never used for lint (no surprise costs)
- Even basic string comparison catches "same concept, different description" cases

---

## Usage Examples

### Applying MindVault to a New Project

```bash
cd my-project
pip install mindvault-ai
mindvault install          # AI Tool Integration + Git hook
mindvault ingest .         # Full build
mindvault status           # Check results
open mindvault-out/graph.html  # Visualize graph in browser
```

### Collecting External Data

```bash
# Collect files
mindvault ingest docs/architecture.pdf

# Collect URLs
mindvault ingest https://example.com/api-docs

# Collect directory contents
mindvault ingest ./references/
```

### Global Mode (Integrating Multiple Projects)

```bash
# Auto-discover sub-projects
mindvault global ~/projects --discover

# Full build
mindvault global ~/projects

# Build + daemon registration (not needed if already registered via install)
mindvault global ~/projects --daemon

# Cross-Project Query
mindvault query "Which projects use the authentication module?" --global
```

### Wiki Integrity Check

```bash
mindvault lint
# Validates [[wikilinks]] in wiki pages
# Detects orphaned nodes and circular references in the graph
# Warns about God Nodes (excessive connections)
```

---

## Dependencies

| Package | Purpose |
|--------|------|
| `networkx` | Graph operations, community detection |
| `tree-sitter` >= 0.23.0 | AST Parsing Engine |
| `tree-sitter-python` | Python AST |
| `tree-sitter-typescript` | TypeScript AST |
| `tree-sitter-javascript` | JavaScript AST |
| `tree-sitter-go` | Go AST |
| `tree-sitter-rust` | Rust AST |
| `tree-sitter-java` | Java AST |
| `tree-sitter-swift` | Swift AST |
| `tree-sitter-kotlin` | Kotlin AST |
| `tree-sitter-c` | C AST |
| `tree-sitter-cpp` | C++ AST |
| `tree-sitter-ruby` | Ruby AST |
| `tree-sitter-c-sharp` | C# AST |

---

## Inspiration

- [LLM Wiki Pattern by Andrej Karpathy](https://x.com/karpathy) — Converting code into a wiki for LLM context efficiency
- [graphify](https://github.com/safishamshi/graphify) — Generating knowledge graphs from codebases
- [llm-wiki-compiler](https://github.com/nicholaschenai/llm-wiki-compiler) — Compiling knowledge into a wiki
- [qmd](https://github.com/nicholaschenai/qmd) — Local BM25 Markdown Search

---

## Changelog (v0.4.2)

**Critical hotfix**: the `UserPromptSubmit` auto-context hook — the core of MindVault's "session continuity" story — had been **silently broken for months**. It exited 0 on every prompt and never injected a single byte of context.

Three chained root causes:
1. It read `$CLAUDE_USER_PROMPT`, an environment variable that does not exist in the Claude Code hook environment. The correct spec is to read the prompt from a stdin JSON payload. Every run started with an empty string and hit the length-guard exit.
2. It used `timeout`, which is not shipped on macOS by default (`gtimeout` via `brew install coreutils` is required). Linux was fine, every macOS install wasn't.
3. The combination was a pure silent-failure pattern — users had no way to notice the hook was doing nothing.

Fixes:
- **`_PROMPT_HOOK_SCRIPT` fully rewritten**: stdin JSON parsing via python3, `gtimeout`/`timeout` fallback, no `set -e`, `MINDVAULT_HOOK_VERSION=2` marker so future upgrades can detect old installs.
- **`install_prompt_hook()` auto-upgrade**: detects hook files that are missing the v2 marker and overwrites them in place. A no-op when already on v2.
- **New CLI command `mindvault doctor`**: 7-step diagnostic — hook file, version marker, executable bit, settings.json registration, `mindvault` on PATH, search index present, and an end-to-end smoke test that feeds the hook a sample JSON prompt and verifies it emits non-empty wrapped output. Exits non-zero if any check fails.
- **17 regression tests added** (109 → 126): script-template invariants, auto-upgrade path, direct shell execution with tmp_path sandboxes, doctor diagnostic smoke test, and a lock against `$CLAUDE_USER_PROMPT` ever appearing in a non-comment line of the hook script again.

Upgrade is automatic: `pip install --upgrade mindvault-ai` then run `mindvault install` once and the broken v1 hook gets replaced by v2. Use `mindvault doctor` to verify.

## Changelog (v0.4.1)

**Hotfix**: fixes a v0.4.0 bug where `export_json` omitted the `schema_version` field, causing already-canonical graphs to re-enter the migration routine on the next incremental run and get their `entity_type` flattened to `entity`.

- **export.py**: `export_json()` now stamps `schema_version: 2` on the graph metadata
- **migrate.py**: canonical-format detection (IDs with ≥ 2 `::` separators) — already-canonical nodes pass through unchanged; only missing `entity_type` is backfilled from the kind slot
- **Regression tests**: 98 → 109 (+11). Covers canonical passthrough, mixed legacy/canonical graphs, `_looks_canonical` detection, and `export_json` schema stamping.

## Changelog (v0.4.0)

**Path-based canonical ID scheme** — node IDs are now derived from file paths.

### What changed

Pre-0.4.0, IDs were `{filestem}_{name}` — just the basename plus the entity name. This produced **collisions** whenever two files shared a basename across directories:

```
src/auth/utils.py::def validate() → utils_validate
src/db/utils.py::def validate()   → utils_validate  ← same ID, nodes merge ❌
```

v0.4.0 uses `{rel_path_slug}::{kind}::{local_slug}`:

```
src/auth/utils.py::validate → src__auth__utils_py::function::validate
src/db/utils.py::validate   → src__db__utils_py::function::validate   ✅
```

### Migration

**Automatic**: if you already have a `graph.json`, the next `mindvault update` (or any incremental run) migrates it in place — takes 1–10 seconds, one-time, no user action required.

**Fallback**: if automatic migration fails (missing `source_file` fields on most nodes, corrupted JSON), you'll see clear instructions:

```bash
rm -rf mindvault-out
mindvault install
```

### Other improvements

- **Pipeline centralization** — `compile()` and `run_incremental()` now share a `_finalize_and_export()` helper, eliminating ~50 LOC of duplicated cluster → wiki → export logic (Codex Finding #9)
- **Test suite grew from 60 → 98** — covers canonical IDs, migration round-trips, Option E fallback, and all prior Codex findings
- **New `entity_type` field** on every node: `file` / `module` / `class` / `function` / `method` / `header` / `block` / `concept`

### Prior releases

- **v0.3.2** — tests/ directory established, 60 regression tests
- **v0.3.1** — 5 Codex patches (Unicode tags, frontmatter line offset, first_header_id, etc.)
- **v0.3.0** — Obsidian native features (frontmatter, inline #tags, recursive walk, `.obsidian/` exclusion)

---

## License

MIT

---

<p align="center">
  <sub>MindVault v0.4.2 | Built by <a href="https://github.com/etinpres">etinpres</a></sub>
</p>
