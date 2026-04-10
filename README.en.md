<p align="center">
  <h1 align="center">MindVault</h1>
  <p align="center">Long-term memory for AI coding tools — auto-converts codebases into knowledge graph + wiki + search index</p>
</p>

<p align="center">
  <a href="https://pypi.org/project/mindvault/"><img src="https://img.shields.io/pypi/v/mindvault?color=blue" alt="PyPI"></a>
  <img src="https://img.shields.io/pypi/pyversions/mindvault" alt="Python 3.10+">
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
pip install mindvault
mindvault install
```

What `mindvault install` performs automatically:
- Detects the currently used AI tool (supports 7)
- Creates integrated configuration files for each tool
- Installs Git post-commit hook (auto-updates on commit)
- Registers Claude Code `/mindvault` Skill

### Requirements

- **Python 3.10+**
- AST-based code structure analysis works without an LLM
- Local LLM or API key required for semantic extraction (see [LLM Setup](#llm-configuration) below)

---

## Quick Start

### CLI Usage

```bash
# Build the knowledge base of the current project
mindvault ingest .

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
Source File / URL / PDF
        |
        v
  [1. Detect]     -- Scans code/document files, automatically detects project with 14 marker files
        |
        v
  [2. Extract]    -- tree-sitter AST → Nodes (function, class, module) + Edges (call, import)
        |
        v
  [3. Semantic]   -- Extracts Why/How/Intent using LLM (Optional)
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

### Output Directory Structure

```
mindvault-out/
├── graph.json           # Original graph data (nodes + edges)
├── graph.html           # vis.js interactive visualization (open in browser)
├── GRAPH_REPORT.md      # Analysis report (God Nodes, Surprising Connections)
├── wiki/
│   ├── INDEX.md         # Wiki entry point (list of all communities)
│   └── *.md             # Wiki pages per community
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
| `mindvault global <root> --daemon` | Build + Daemon registration |

### Daemon Management

| Command | Description |
|--------|------|
| `mindvault daemon status` | Checks daemon status |
| `mindvault daemon stop` | Stops the daemon |
| `mindvault daemon log` | Checks daemon logs |

### Configuration

| Command | Description |
|--------|------|
| `mindvault config llm <url>` | Sets the LLM endpoint |
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
# Manually set LLM endpoint
mindvault config llm http://localhost:8080

# Auto-approve API usage (no prompting)
mindvault config auto-approve true

# Check current configuration
mindvault config show
```

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

Registering with `mindvault global <root> --daemon` enables automatic background updates using the OS's native service manager.

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

## Usage Examples

### Applying MindVault to a New Project

```bash
cd my-project
pip install mindvault
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

# Build + Daemon Registration (Background automatic updates)
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

## License

MIT

---

<p align="center">
  <sub>MindVault v0.1.0 | Built by <a href="https://github.com/etinpres">etinpres</a></sub>
</p>