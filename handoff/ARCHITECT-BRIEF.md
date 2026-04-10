# ARCHITECT-BRIEF — MindVault

## Step 9 — Semantic Extraction (LLM Auto-Detect + Consent)

**Goal**: extract_semantic을 실제 구현. 로컬 LLM 자동 감지, API 키 호출 시 사용자 동의, PDF/URL/이미지 지원. 이 Step 완료 후 `mindvault ingest paper.pdf`가 동작해야 함.

**Scope**: extract.py 확장, llm.py (신규), config.py (신규), ingest.py (신규), cli.py 확장

---

### 9.1 config.py — 사용자 설정 관리

```python
def load_config() -> dict:
def save_config(config: dict) -> None:
def get(key: str, default=None):
def set(key: str, value):
```

**구현**:
- 설정 파일: `~/.mindvault/config.json`
- 기본값:
  ```json
  {
    "llm_endpoint": null,
    "auto_approve_api": false,
    "max_tokens_per_file": 4000,
    "preferred_provider": null
  }
  ```
- `llm_endpoint`: 사용자가 직접 지정한 LLM URL (null이면 자동 감지)
- `auto_approve_api`: true면 API 호출 시 묻지 않음
- `preferred_provider`: "gemma", "ollama", "anthropic", "openai" 중 지정 가능

---

### 9.2 llm.py — LLM 자동 감지 + 호출

```python
def detect_llm() -> dict:
def call_llm(prompt: str, text: str, provider: dict = None) -> str:
def estimate_cost(text: str, provider: dict) -> float:
def confirm_api_usage(provider: dict, cost: float) -> bool:
```

**detect_llm** — 우선순위대로 자동 감지:
1. `config.llm_endpoint`가 설정되어 있으면 그것 사용
2. `http://localhost:8080` 핑 → Gemma MLX 서버
3. `http://localhost:11434` 핑 → Ollama
4. `ANTHROPIC_API_KEY` 환경변수 → Anthropic (haiku)
5. `OPENAI_API_KEY` 환경변수 → OpenAI (gpt-4o-mini)
6. 없음

- 핑 = `/v1/models` 또는 `/api/tags` GET, timeout 2초
- 반환:
  ```python
  {
    "provider": "gemma" | "ollama" | "anthropic" | "openai" | None,
    "endpoint": "http://...",
    "model": "gemma-4-e4b" | "haiku" | "gpt-4o-mini",
    "is_local": True | False,
    "api_key": "sk-..." | None,
  }
  ```

**call_llm** — OpenAI-compatible API 호출:
- 로컬 (Gemma/Ollama): `POST {endpoint}/v1/chat/completions`
  ```json
  {"model": "...", "messages": [{"role": "user", "content": "..."}], "temperature": 0.3}
  ```
- Anthropic: `POST https://api.anthropic.com/v1/messages`
  ```json
  {"model": "claude-haiku-4-5-20251001", "max_tokens": 4000, "messages": [...]}
  ```
  헤더: `x-api-key`, `anthropic-version: 2023-06-01`
- OpenAI: `POST https://api.openai.com/v1/chat/completions`
  ```json
  {"model": "gpt-4o-mini", "messages": [...]}
  ```
- 순수 `urllib.request` 사용 (requests 의존성 없이)

**estimate_cost** — 대략적 API 비용 추정:
- Haiku: input $0.80/M tokens, output $4.00/M tokens
- GPT-4o-mini: input $0.15/M tokens, output $0.60/M tokens
- 로컬: $0.00
- 텍스트 길이 / 4 로 토큰 수 추정

**confirm_api_usage** — API 호출 전 사용자 동의:
- `auto_approve_api`가 true면 바로 True 반환
- 아니면 stdout에 경고 출력 후 `input()` 대기:
  ```
  ⚠️  No local LLM detected. Using Anthropic Haiku (API key found).
      Estimated cost for this file: ~$0.02
      Continue? [y/N]: 
  ```
- CLI가 아닌 환경(subprocess 등)에서는 auto_approve가 아니면 False 반환

---

### 9.3 ingest.py — 외부 자료 수집

```python
def ingest_file(file_path: Path, output_dir: Path) -> dict:
def ingest_url(url: str, output_dir: Path) -> dict:
def ingest(source: str, output_dir: Path) -> dict:
```

**ingest** — 진입점:
- URL이면 `ingest_url` 호출
- 파일이면 `ingest_file` 호출
- 디렉토리면 하위 파일 각각 `ingest_file`

**ingest_file**:
- 파일을 `output_dir/sources/` 에 복사
- 텍스트 추출:
  - `.md`, `.txt`, `.rst`: 직접 읽기
  - `.pdf`: `subprocess`로 `pdftotext` 호출 (없으면 순수 Python 바이너리 파싱으로 fallback — 간단 구현)
  - `.png`, `.jpg`, `.webp`: 이미지는 현재 skip (vision API 연동은 Known Gap)
- LLM에 개념/관계 추출 요청 (detect_llm → call_llm)
- 추출 결과를 기존 graph에 병합
- 반환: `{nodes: int, edges: int, source: str}`

**ingest_url**:
- URL fetch: `urllib.request.urlopen` 
- HTML → markdown 변환: 간단한 태그 제거 (`<script>`, `<style>` 제거 → 텍스트만)
- YouTube URL 감지: `youtube.com`, `youtu.be` → `yt-dlp --write-auto-sub` 자막 추출 시도 (없으면 skip)
- 저장: `output_dir/sources/{slug}.md`
- 이후 `ingest_file`과 동일하게 LLM 추출

**LLM 추출 프롬프트**:
```
Extract key concepts and relationships from this text.
Return JSON only:
{
  "nodes": [{"id": "slug_name", "label": "Human Name", "file_type": "document", "source_file": "path"}],
  "edges": [{"source": "id1", "target": "id2", "relation": "references|implements|related_to", "confidence": "EXTRACTED|INFERRED", "confidence_score": 0.8}]
}

Rules:
- Extract named concepts, entities, technologies, decisions
- EXTRACTED: explicitly stated relationship
- INFERRED: reasonable inference
- Keep nodes under 30 per document
- Keep edges under 50 per document
```

---

### 9.4 extract.py — extract_semantic 구현

```python
def extract_semantic(files: list[Path], cache_dir: Path) -> dict:
```

**구현**:
1. `detect_llm()` → LLM 감지
2. LLM 없으면 → 빈 결과 반환 (에러 아님)
3. API 키면 → `confirm_api_usage()` → 거부 시 빈 결과
4. 각 파일에 대해:
   - `cache.is_dirty()` → 변경된 파일만
   - 텍스트 읽기
   - `call_llm(extraction_prompt, text)` → JSON 파싱
   - 캐시 업데이트
5. 모든 결과 병합 반환

---

### 9.5 compile.py 수정

현재: `extract_ast`만 호출
변경: `extract_ast` + `extract_semantic` 둘 다 호출, 결과 병합

```python
# 기존
extraction = extract_ast(code_files)

# 변경
ast_result = extract_ast(code_files)
doc_files = [source_dir / f for f in detection["files"].get("document", [])]
sem_result = extract_semantic(doc_files, output_dir)
extraction = merge_extractions(ast_result, sem_result)
```

---

### 9.6 cli.py 확장

```
mindvault config llm http://localhost:8080    # LLM 엔드포인트 설정
mindvault config auto-approve true            # API 자동 승인
mindvault config show                         # 현재 설정 표시
```

`cmd_ingest` 업데이트:
- URL 감지 → `ingest_url`
- 파일/디렉토리 → `ingest_file`
- 결과 출력

---

### 9.7 테스트 시나리오

```bash
# Test 1: LLM auto-detect (Gemma should be found on this machine)
python3 -c "
from mindvault.llm import detect_llm
result = detect_llm()
print(f'Provider: {result[\"provider\"]}')
print(f'Endpoint: {result[\"endpoint\"]}')
print(f'Local: {result[\"is_local\"]}')
assert result['provider'] is not None, 'No LLM detected'
print('PASS')
"

# Test 2: Call local LLM with extraction prompt
python3 -c "
from mindvault.llm import detect_llm, call_llm
provider = detect_llm()
result = call_llm(
    'Extract 3 key concepts from this text as JSON: {\"concepts\": [\"...\", ...]}',
    'MindVault is a knowledge management tool that creates graphs and wikis from code.',
    provider
)
print(f'LLM response: {result[:200]}')
print('PASS')
"

# Test 3: Ingest a markdown file
python3 -c "
from mindvault.ingest import ingest
from pathlib import Path
result = ingest('/Users/yonghaekim/my-folder/apps/mindvault/README.md', Path('/Users/yonghaekim/my-folder/apps/mindvault/mindvault-out'))
print(f'Ingested: {result}')
assert result.get('nodes', 0) > 0 or result.get('skipped', False), 'Should extract or skip'
print('PASS')
"

# Test 4: extract_semantic on doc files
python3 -c "
from mindvault.extract import extract_semantic
from pathlib import Path
result = extract_semantic(
    [Path('/Users/yonghaekim/my-folder/apps/mindvault/README.md')],
    Path('/Users/yonghaekim/my-folder/apps/mindvault/mindvault-out')
)
print(f'Nodes: {len(result[\"nodes\"])}, Edges: {len(result[\"edges\"])}')
print('PASS')
"

# Test 5: Config
python3 -c "
from mindvault.config import load_config, get, set as set_config
cfg = load_config()
print(f'Config: {cfg}')
set_config('auto_approve_api', False)
assert get('auto_approve_api') == False
print('PASS')
"

# Test 6: Full pipeline with semantic (README.md should be extracted)
python3 -c "
from mindvault.pipeline import run
from pathlib import Path
import shutil
out = Path('/Users/yonghaekim/my-folder/apps/mindvault/mindvault-out')
if out.exists(): shutil.rmtree(out)
result = run(Path('/Users/yonghaekim/my-folder/apps/mindvault'), out)
print(f'Nodes: {result[\"nodes\"]}, Edges: {result[\"edges\"]}')
print(f'Wiki: {result[\"wiki_pages\"]}, Index: {result[\"index_docs\"]}')
print('PASS')
"
```

---

### 9.8 Constraints

- **urllib만 사용** — requests 의존성 추가하지 않음
- API 호출 비용은 **반드시 사전 고지** (auto_approve가 아닌 경우)
- 로컬 LLM은 **동의 없이** 바로 호출
- PDF 텍스트 추출: pdftotext가 없으면 skip (에러 아님)
- 이미지 vision 분석은 **Known Gap** — 이 Step에서 미구현
- LLM JSON 파싱 실패 → 해당 파일 skip, 전체 중단 금지
- timeout: LLM 호출 60초, URL fetch 30초

### 9.9 Acceptance Criteria

1. `detect_llm()` → Gemma 감지 (이 머신에서)
2. `call_llm()` → 로컬 LLM 응답 수신
3. `ingest(README.md)` → 개념 추출 성공
4. `extract_semantic()` → nodes + edges 반환
5. Config 저장/로드 동작
6. Full pipeline이 시맨틱 추출 포함해서 실행
7. 6개 테스트 모두 PASS
