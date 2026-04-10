# REVIEW-REQUEST — Step 9: Semantic Extraction (LLM Auto-Detect + Consent)

**Builder**: Bob
**Date**: 2026-04-09
**Step**: 9 — Semantic Extraction (LLM Auto-Detect + Consent)

## Files Created/Modified

### New files (3)
1. **`src/mindvault/config.py`** — User settings in `~/.mindvault/config.json`
   - `load_config()`, `save_config()`, `get()`, `set()`
   - Keys: `llm_endpoint`, `auto_approve_api`, `max_tokens_per_file`, `preferred_provider`
   - Merges user values with defaults on load

2. **`src/mindvault/llm.py`** — LLM auto-detection + calling (urllib only)
   - `detect_llm()`: priority — config override → Gemma:8080 → Ollama:11434 → ANTHROPIC_API_KEY → OPENAI_API_KEY
   - `_detect_gemma_model()`: queries `/v1/models` to discover actual model ID (handles MLX server naming like `mlx-community/gemma-4-e4b-it-4bit`)
   - `call_llm()`: OpenAI-compatible for local, Anthropic Messages API for Claude, OpenAI API for GPT
   - `estimate_cost()`: token estimate (len/4) * price per model
   - `confirm_api_usage()`: prints warning + input() for non-auto-approve, returns False if not interactive

3. **`src/mindvault/ingest.py`** — External source ingestion
   - `ingest()`: entry point, detects file vs URL vs directory
   - `ingest_file()`: copy to sources/, extract text, call LLM for concept extraction
   - `ingest_url()`: fetch URL, strip HTML, save as .md, then ingest_file
   - Text extraction: .md/.txt/.rst direct, .pdf via pdftotext (skip if unavailable), images skip

### Modified files (4)
4. **`src/mindvault/extract.py`** — `extract_semantic()` fully implemented:
   - detect_llm → if none, return empty
   - API consent check (batch, once) → if denied, return empty
   - Per-file: cache check → read text → call_llm → parse JSON → cache update
   - JSON parse failure → warning to stderr, skip file, continue

5. **`src/mindvault/compile.py`** — Calls both `extract_ast` AND `extract_semantic`, merges via `_merge_extractions()`

6. **`src/mindvault/cli.py`** — Added `config` subcommand (llm, auto-approve, provider, show). Updated `cmd_ingest` to handle URLs and document files directly.

7. **`src/mindvault/__init__.py`** — Added re-exports for config, llm, and ingest modules.

## Test Results (all 6 PASS)

| # | Test | Result | Detail |
|---|------|--------|--------|
| 1 | `detect_llm()` | PASS | Gemma at localhost:8080, model `mlx-community/gemma-4-e4b-it-4bit` |
| 2 | `call_llm()` local | PASS | Gemma returns JSON with 3 extracted concepts |
| 3 | `ingest(README.md)` | PASS | 13 nodes, 14 edges extracted |
| 4 | `extract_semantic()` | PASS | 10 nodes, 10 edges from doc files |
| 5 | Config save/load | PASS | Persists to `~/.mindvault/config.json` |
| 6 | Full pipeline | PASS | 271 nodes, 373 edges, 40 wiki pages, 52 index docs |

## Review Focus Areas

1. **Gemma model auto-discovery**: `_detect_gemma_model()` queries `/v1/models` and picks the first model with "gemma" in its ID. If the MLX server hosts multiple models, it prefers gemma but falls back to the first listed model. This is correct for the current setup but may need refinement if the server loads non-gemma models.

2. **LLM response parsing**: Gemma 4 returns a `reasoning` field alongside `content` in its chat completions response. The code correctly accesses only `message["content"]`. JSON code blocks (```json...```) are stripped before parsing.

3. **Semantic extraction caching**: Uses the same SHA256 cache as AST extraction. Files already cached from `ingest()` won't be re-processed by `extract_semantic()` (and vice versa). This is intentional — prevents duplicate LLM calls.

4. **API cost consent**: Only prompted once per `extract_semantic()` batch (not per-file). Local LLM gets no prompt. The `confirm_api_usage()` returns False in non-interactive contexts unless `auto_approve_api` is set.

5. **max_tokens**: `max_tokens: 4000` is sent to local models to prevent truncation. Without this, the Gemma MLX server defaults to a lower limit and returns `finish_reason: length`.

## Acceptance Criteria Check

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `detect_llm()` → Gemma detected on this machine | YES |
| 2 | `call_llm()` → local LLM response received | YES |
| 3 | `ingest(README.md)` → concepts extracted | YES |
| 4 | `extract_semantic()` → nodes + edges returned | YES |
| 5 | Config save/load works | YES |
| 6 | Full pipeline includes semantic extraction | YES |
| 7 | All 6 tests PASS | YES |
