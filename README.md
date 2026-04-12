<p align="center">
  <h1 align="center">MindVault</h1>
  <p align="center">AI 코딩 도구의 "장기 기억" — 코드베이스를 자동으로 지식 그래프 + 위키 + 검색 인덱스로 변환</p>
</p>

<p align="center">
  <a href="https://pypi.org/project/mindvault-ai/"><img src="https://img.shields.io/pypi/v/mindvault-ai?color=blue" alt="PyPI"></a>
  <img src="https://img.shields.io/pypi/pyversions/mindvault-ai" alt="Python 3.10+">
  <img src="https://img.shields.io/github/license/etinpres/mindvault" alt="MIT License">
</p>

[English](README.en.md) | **한국어**

---

## 왜 MindVault인가?

AI 코딩 도구(Claude Code, Cursor, Copilot 등)는 **세션이 끝나면 맥락을 전부 잊어버립니다.** 새 세션을 열 때마다 "이 프로젝트는 이런 구조고, 이 함수는 이렇게 동작하고..."를 반복 설명해야 합니다. 이건 **시간 낭비이자 토큰 낭비**입니다.

기존에는 이 문제를 해결하기 위해 3개의 도구가 각각 존재했습니다:

| 기존 도구 | 역할 | 한계 |
|-----------|------|------|
| **qmd** | BM25 로컬 검색 | 검색만 가능, 관계 파악 불가 |
| **graphify** | 지식 그래프 생성 | 검색/위키 없음 |
| **llm-wiki-compiler** | 위키 컴파일 | 그래프/검색 없음 |

MindVault는 이 3개의 장점을 **설치 한 줄, 설정 제로**로 통합합니다. [Andrej Karpathy의 LLM Wiki 패턴](https://x.com/karpathy)에서 영감을 받았습니다.

---

## 3-Layer 아키텍처

```
                    질의: "인증은 어떻게 동작하나요?"
                              |
                    +---------v---------+
                    |  1. Search Layer  |  BM25 로컬 검색
                    |  (토큰 소비: 0)   |  한국어/영어/CJK 지원
                    +---------+---------+
                              |
                    +---------v---------+
                    |  2. Graph Layer   |  지식 그래프 탐색
                    |  (토큰 ~100)      |  BFS/DFS 이웃 노드
                    +---------+---------+
                              |
                    +---------v---------+
                    |  3. Wiki Layer    |  커뮤니티 위키 읽기
                    |  (토큰 ~800)      |  Why/How 컨텍스트
                    +---------+---------+
                              |
                        답변 생성
                    (질의당 총 ~900 토큰)
```

| Layer | 역할 | 토큰 소비 | 기술 |
|-------|------|-----------|------|
| **Search** | 키워드 매칭으로 관련 위키 페이지 발견 | 0 (로컬 연산) | BM25 역색인 |
| **Graph** | 매칭된 노드의 관계/이웃 탐색 | ~100 | NetworkX BFS/DFS |
| **Wiki** | 커뮤니티 페이지에서 컨텍스트 추출 | ~800 | 마크다운 위키 |
| **합계** | | **~900** | 원본 직접 읽기 대비 **60배+ 절감** |

---

## 설치

```bash
pip install mindvault-ai
mindvault install
```

`mindvault install`이 자동으로 수행하는 작업:
- 현재 사용 중인 AI 도구 감지 (10개 지원)
- 각 도구별 통합 설정 파일 생성
- Git post-commit hook 설치 (커밋마다 자동 갱신)
- Claude Code `/mindvault` Skill 등록
- **Auto-context hook 설치** — 모든 질문에 MindVault 컨텍스트 자동 주입 (시스템 레벨)

### 요구사항

- **Python 3.10+**
- **파이썬 의존성 (pip install 시 자동 설치)**
  - `networkx` — 지식 그래프 엔진
  - `tree-sitter` + 13개 언어 파서 — AST 기반 코드 구조 분석
  - `python-docx`, `openpyxl`, `python-pptx` — Office 문서(.docx/.xlsx/.pptx) 추출 (v0.2.7+)
- **선택적 시스템 바이너리**
  - `pdftotext` — PDF 추출 시 필요 (macOS: `brew install poppler`, Ubuntu: `apt install poppler-utils`, Windows: [Xpdf tools](https://www.xpdfreader.com/download.html))
- LLM 없이도 AST 기반 코드 구조 분석 동작
- 시맨틱 추출 시 로컬 LLM 또는 API 키 필요 (아래 [LLM 설정](#llm-설정) 참고)

---

## 빠른 시작

### 1. 설치 및 초기화

```bash
pip install mindvault-ai
cd ~/your-project
mindvault install .    # hooks + 데몬 자동 등록 (5분마다 변경 감지)
```

초기 지식 베이스 구축은 두 가지 방법이 있습니다:

```bash
# 방법 A: 단일 프로젝트만 빌드
mindvault ingest .

# 방법 B: 여러 프로젝트를 한번에 통합 빌드
mindvault global ~/projects
```

| 명령어 | 대상 | 용도 |
|--------|------|------|
| `mindvault ingest .` | 현재 폴더 1개 | 특정 프로젝트만 빠르게 빌드 |
| `mindvault global <root>` | 하위 모든 프로젝트 | 프로젝트 간 관계까지 통합 빌드 |

> 초기 빌드 이후에는 데몬이 5분마다 변경 사항을 자동 감지하여 업데이트합니다.
> 데몬이 필요 없으면 `mindvault install . --no-daemon`

#### 루트 폴더 밖의 파일 인덱싱

루트 경로 밖에 있는 파일/폴더도 `mindvault ingest`로 수동 인덱싱할 수 있습니다:

```bash
# 예: 홈 디렉토리의 설정 스크립트 인덱싱
mindvault ingest ~/.config/my-tool/

# 예: 다른 경로의 문서 폴더 인덱싱
mindvault ingest /opt/docs/api-reference/
```

> **주의:** 루트 폴더 밖의 경로는 데몬 자동 감시 대상에 포함되지 않습니다. 해당 파일이 변경되면 `mindvault ingest`를 다시 실행해야 합니다.

#### 지원하는 문서 포맷

| 포맷 | 상태 | 비고 |
|------|------|------|
| `.md`, `.txt`, `.rst` | ✅ 기본 지원 | — |
| `.pdf` | ✅ 기본 지원 | 시스템에 `pdftotext` 필요 |
| `.docx`, `.xlsx`, `.pptx` | ✅ v0.2.7+ 기본 지원 | Word / Excel / PowerPoint 자동 인식 |
| `.json`, `.yaml`, `.yml` | ✅ v0.5.0+ 기본 지원 | 구조화 데이터 자동 인덱싱 (아래 참고) |

추가 설치 없이 `mindvault ingest /path/to/문서폴더` 만 실행하면 위 포맷을 전부 자동 추출합니다.

### 2. 사용

```bash
# 3-layer 통합 질의
mindvault query "인증은 어떻게 동작하나요?"

# DFS 모드 (특정 호출 체인 깊게 추적)
mindvault query "이 함수의 전체 호출 경로는?" --dfs

# 현재 상태 확인
mindvault status
```

### Claude Code Skill 사용

```
/mindvault .
/mindvault query "파이프라인 동작 방식은?"
```

---

## 동작 원리

```
소스 파일 / URL / PDF / 문서
        |
        v
  [1. Detect]     -- 코드/문서/PDF/이미지 파일 탐색, 14개 마커 파일로 프로젝트 자동 감지
        |
        v
  [2. Extract]    -- 코드: tree-sitter AST (함수, 클래스, import)
        |             문서: 구조 추출 (헤더 계층, 링크, 코드블록) ← LLM 불필요
        |             PDF: 섹션 구조 추출
        |             JSON/YAML: 키-값 추출 (title, tags → 그래프 노드)
        v
  [3. Semantic]   -- LLM으로 의미/의도 분석 (선택사항, 코드+문서 모두)
        |
        v
  [4. Build]      -- NetworkX DiGraph 구축, 댕글링 엣지 필터링
        |
        v
  [5. Cluster]    -- 그리디 모듈러리티 커뮤니티 탐지
        |
        v
  [6. Wiki]       -- 커뮤니티별 마크다운 위키 자동 생성 (Obsidian [[wikilinks]] 호환)
        |
        v
  [7. Index]      -- BM25 역색인 구축 (한국어/영어/CJK)
        |
        v
    mindvault-out/
```

> **참고**: 2단계(Extract)는 입력 유형에 따라 자동 분기합니다. 코드 파일은 AST 분석, 문서/PDF는 구조 추출을 수행합니다. 두 경로 모두 LLM이 필요하지 않으며 토큰 소비 0입니다. 3단계(Semantic)는 LLM이 있을 때만 실행되며, 코드와 문서 모두에 적용됩니다.

### 출력 디렉토리 구조

```
mindvault-out/
├── graph.json           # 원본 그래프 데이터 (노드 + 엣지)
├── graph.html           # vis.js 인터랙티브 시각화 (브라우저에서 열기)
├── GRAPH_REPORT.md      # 분석 리포트 (God Nodes, Surprising Connections)
├── wiki/
│   ├── INDEX.md         # 위키 진입점 (전체 커뮤니티 목록)
│   ├── *.md             # 커뮤니티별 위키 페이지
│   ├── _concepts.json   # 개념 인덱스 (상호참조용)
│   ├── ingested/        # 외부 자료에서 추출한 지식 페이지
│   └── queries/         # 저장된 질의/답변 기록
├── search_index.json    # BM25 검색 인덱스
└── sources/             # 수집된 외부 자료 (URL, PDF 등)
```

---

## CLI 명령어 레퍼런스

### 핵심 명령어

| 명령어 | 설명 |
|--------|------|
| `mindvault install` | AI 도구 감지 + 통합 설정 + Git hook + Skill 등록 |
| `mindvault ingest <path/url>` | 파일/URL/폴더 수집 → 그래프+위키+인덱스 자동 갱신 |
| `mindvault query "<question>"` | 3-layer 통합 질의 (search → graph → wiki) |
| `mindvault status` | 현재 그래프/위키/인덱스 상태 표시 |

### 질의 옵션

| 명령어 | 설명 |
|--------|------|
| `mindvault query "<question>"` | 기본 BFS 모드 (넓은 탐색) |
| `mindvault query "<question>" --dfs` | DFS 모드 (깊은 호출 체인 추적) |
| `mindvault query "<question>" --global` | 글로벌 인덱스에서 크로스 프로젝트 검색 |

### 갱신 & 감시

| 명령어 | 설명 |
|--------|------|
| `mindvault update` | incremental 갱신 (git hook이 자동 호출) |
| `mindvault watch` | 파일 변경 실시간 감시 (polling 기반) |
| `mindvault mark-dirty <path>` | 특정 파일을 dirty로 표시 (재추출 대상) |
| `mindvault flush` | dirty 파일 일괄 처리 |

### 글로벌 모드

| 명령어 | 설명 |
|--------|------|
| `mindvault global <root>` | 모든 하위 프로젝트 통합 빌드 |
| `mindvault global <root> --discover` | 프로젝트 목록만 출력 (빌드 안 함) |
| `mindvault global <root> --daemon` | 빌드 + 데몬 등록 (install에서 이미 등록된 경우 불필요) |

### 데몬 관리

> 데몬은 `mindvault install` 시 자동 등록됩니다. 아래 명령어로 상태 확인/관리할 수 있습니다.

| 명령어 | 설명 |
|--------|------|
| `mindvault daemon status` | 데몬 상태 확인 |
| `mindvault daemon stop` | 데몬 중지 |
| `mindvault daemon log` | 데몬 로그 확인 |

### 설정

| 명령어 | 설명 |
|--------|------|
| `mindvault config llm <url>` | LLM 엔드포인트 설정 |
| `mindvault config auto-approve true/false` | API 호출 자동 승인 설정 |
| `mindvault config show` | 현재 설정 표시 |
| `mindvault lint` | 위키 정합성 + 그래프 건강 검사 |
| `mindvault --version` | 버전 확인 |

---

## 토큰 절감 벤치마크

### 단일 프로젝트

| 시나리오 | 원본 직접 읽기 | MindVault 질의 | 절감 배수 |
|----------|---------------|----------------|-----------|
| 소규모 (20 파일) | ~15,000 토큰 | ~900 토큰 | **17x** |
| 중규모 (100 파일) | ~60,000 토큰 | ~900 토큰 | **67x** |
| 대규모 (500 파일) | ~300,000 토큰 | ~900 토큰 | **333x** |

### 실제 측정 (MindVault 자체 소스, 24 파일)

| 지표 | 수치 |
|------|------|
| 노드 수 | 271 |
| 엣지 수 | 373 |
| 위키 페이지 | 40 |
| 질의당 토큰 | ~900 |

### 글로벌 모드 (9개 프로젝트 통합)

| 지표 | 수치 |
|------|------|
| 노드 수 | 572 |
| 엣지 수 | 670 |
| 크로스 프로젝트 연결 | 33 |

### 실측 A/B 비교 (Claude Code Opus 4.6, 동일 질문)

> **질문**: 과거 프로젝트에서 해결했던 Android 네이티브 버그의 수정 방법을 질문

| | MindVault OFF | MindVault ON |
|---|---|---|
| 서브에이전트 호출 | 1회 (Explore) | 0회 |
| 도구 호출 | 6회 | 0회 |
| 탐색 토큰 | 61,800+ | ~0 (메모리만) |
| 응답 시간 | ~55초 | 즉시 |

MindVault auto-context 훅이 프로젝트 맥락을 사전 주입하므로, 파일 탐색 없이 즉답이 가능합니다.

질의 토큰 버짓은 `--budget` 옵션으로 조정 가능합니다 (기본값: 5000 토큰).

---

## 지원 프로그래밍 언어

tree-sitter 기반 AST 추출을 지원하는 13개 언어:

| 언어 | 언어 | 언어 |
|------|------|------|
| Python | TypeScript | JavaScript |
| Go | Rust | Java |
| Swift | Kotlin | C |
| C++ | Ruby | C# |
| Scala | PHP | Lua |

---

## AI 도구 자동 연동

`mindvault install` 실행 시 감지된 도구에 맞는 설정 파일을 자동 생성합니다.

| AI 도구 | 생성되는 설정 파일 |
|---------|-------------------|
| **Claude Code** | `CLAUDE.md` + `SKILL.md` |
| **Cursor** | `.cursorrules` |
| **GitHub Copilot** | `.github/copilot-instructions.md` |
| **Windsurf** | `.windsurfrules` |
| **Gemini Code Assist** | `.gemini/styleguide.md` |
| **Cline** | `.clinerules` |
| **Aider** | `CONVENTIONS.md` |
| **AGENTS.md Standard** (OpenAI Codex CLI, Google Antigravity 등) | `AGENTS.md` |
| **Google Gemini CLI** | `GEMINI.md` |
| **Qwen Code** | `QWEN.md` |

---

## Obsidian에서 결과물 보기 (선택 사항)

> MindVault는 **Claude Code / Codex / Cursor 등 AI 코딩 도구를 쓰는 개발자**를 위해 설계된 CLI 도구입니다. Obsidian 없이도 단독으로 완전히 작동합니다. 아래 내용은 이미 Obsidian을 쓰고 있거나, MindVault 결과물을 더 예쁘게 탐색하고 싶은 경우에만 해당됩니다.

**Obsidian 플러그인은 따로 없습니다.** MindVault는 그냥 마크다운을 출력할 뿐이고, Obsidian은 그 폴더를 vault로 열면 backlink / graph view / 검색을 자동으로 제공합니다. 별도 의존성이 추가되지 않습니다.

### 패턴 A: MindVault 출력물을 Obsidian vault로 열기 (가장 흔한 사용)

코드베이스를 먼저 인덱싱합니다:

```bash
mindvault ingest .
```

그러면 `mindvault-out/wiki/` 폴더에 커뮤니티별 마크다운 위키 페이지가 생성됩니다. 이 폴더를 **Obsidian에서 vault로 열면** 다음이 자동으로 작동합니다:

- ✅ Obsidian 그래프 뷰에 MindVault 지식 그래프 시각화
- ✅ `[[링크]]` 양방향 네비게이션
- ✅ 검색 / 태그 / 백링크 / 아웃라인 패널 전부 활용

Andrej Karpathy의 LLM Wiki 패턴을 **자동 생성 + Obsidian UI**로 즉시 사용하는 효과입니다.

### 패턴 B: 기존 Obsidian vault 인덱싱 (Python + Claude Code 필요)

> 이 패턴은 순수 Obsidian 유저용이 **아닙니다**. Python 3.10+ 설치, `pip install mindvault-ai`, 그리고 시맨틱 추출을 쓰려면 Claude Code 또는 로컬 LLM이 필요합니다. AI 도구를 이미 쓰고 있는 개발자가 기존 vault의 지식 그래프를 만들고 싶을 때 적합합니다.

이미 사용 중인 Obsidian vault가 있으면 그대로 인덱싱할 수 있습니다:

```bash
mindvault ingest ~/my-obsidian-vault
```

MindVault가 자동으로 처리하는 것:

- `.md` 파일 헤더 → 그래프 노드
- `[[wikilinks]]` → 그래프 엣지 (기존 vault의 연결 구조 보존)
- BM25 검색 인덱스 자동 구축

그 후 3-layer 질의를 기존 vault에 그대로 올릴 수 있습니다:

```bash
mindvault query "프로젝트 R의 주요 결정사항"
```

### 패턴 C: 코드 + 노트 통합 검색

코드 프로젝트(패턴 A)와 Obsidian 노트(패턴 B)를 **둘 다** 인덱싱해두면 하나의 지식 그래프로 연결됩니다:

```bash
mindvault global ~/projects          # 코드 프로젝트 전체
mindvault ingest ~/my-obsidian-vault # 노트 vault
mindvault query "인증 모듈의 설계 배경" --global
```

→ 코드 구조(Graph Layer) + Obsidian 노트의 설계 결정(Wiki Layer)이 하나의 답변에 통합됩니다.

> **Tip**: Obsidian의 "Folder as vault" 기능으로 `mindvault-out/wiki/`를 바로 열 수 있습니다. 별도 복사나 심볼릭 링크 불필요.

### Obsidian 네이티브 기능 지원 (v0.3.0+)

v0.3.0부터 Obsidian vault 인덱싱 시 다음 기능이 자동으로 동작합니다:

| 기능 | 설명 |
|------|------|
| **YAML frontmatter 파싱** | `---` 블록의 `title`, `tags`, `aliases` 등 메타데이터를 첫 번째 헤더 노드(또는 파일 노드)에 자동 부착 |
| **인라인 `#tags` 추출** | 본문 내 `#project`, `#auth`, `#nested/tag` 등을 자동 수집 (숫자/HTML 컬러 코드는 제외) |
| **재귀 디렉토리 순회** | `mindvault ingest ~/my-vault` 가 하위 폴더 전체를 자동 탐색 |
| **자동 exclude** | `.obsidian/`, `.trash/`, `.stfolder/`, `.stversions/` 등 내부 디렉토리 건너뜀 |

예시 — 프론트매터가 있는 Obsidian 노트:

```markdown
---
title: Auth Rewrite Plan
tags: [project, auth, 2026-q2]
status: in-progress
---

# Auth Rewrite Plan

#architecture 관련 결정은 [[ADR-007]]에 정리됨. #security 리뷰 통과 후 배포.
```

→ 이 파일은 `metadata: {title, tags, status}`가 헤더 노드에 부착되고, `#architecture`, `#security` 태그가 노드에 추가되며, `[[ADR-007]]` 링크는 그래프 엣지로 변환됩니다.

---

## LLM 설정

MindVault는 시맨틱 추출(코드의 의도/목적 분석)을 위해 LLM을 사용합니다. **LLM이 없어도 AST 기반 구조 분석은 정상 동작합니다.**

### 자동 감지 순서

로컬 LLM을 우선 탐색하고, 없으면 구독 토큰 또는 API를 사용합니다:

| 우선순위 | LLM | 방식 | 비용 | 사전 동의 |
|----------|-----|------|------|-----------|
| 1 | **Gemma (로컬)** | `localhost:8080` | 무료 | 불필요 |
| 2 | **Ollama (로컬)** | `localhost:11434` | 무료 | 불필요 |
| 3 | **Claude Code Skill** | `/mindvault` 실행 시 | 구독 토큰 | 불필요 |
| 4 | **Anthropic Claude Haiku** | API 키 | 유료 | **필수** |
| 5 | **OpenAI GPT-4o-mini** | API 키 | 유료 | **필수** |
| 6 | **LLM 없음** | — | 무료 | — |

- **로컬 LLM**: 동의 없이 바로 호출 (무료)
- **Claude Code 구독자**: `/mindvault` skill로 실행하면 Claude 자체가 추출을 수행합니다. 별도 API 키 없이 구독 토큰만 사용.
- **API 키 사용**: 예상 비용을 표시하고 사용자 동의를 구한 후에만 호출합니다.
- **LLM 없음**: AST 기반 코드 구조 분석은 정상 동작합니다. 시맨틱 추출(문서 의미 분석)만 건너뜁니다.

> **대부분의 사용자는 Claude Code/Cursor/Copilot 구독자입니다.** `/mindvault` skill로 실행하면 추가 설정 없이 시맨틱 추출이 동작합니다.

```bash
# 일반 LLM 엔드포인트 수동 설정 (OpenAI-compatible)
mindvault config llm http://localhost:8080

# Ollama 호스트 오버라이드 (WSL → Windows 호스트 Ollama 등)
mindvault config ollama-host http://172.28.112.1:11434
# OLLAMA_HOST 환경변수도 자동 인식됩니다

# 사용할 모델명 강제 지정 (자동 탐지 결과보다 우선)
mindvault config llm-model gemma3:e4b
mindvault config llm-model qwen3:4b

# API 자동 승인 (매번 묻지 않음)
mindvault config auto-approve true

# 현재 설정 확인
mindvault config show
```

> **v0.2.9+**: Ollama는 설치된 모델 목록을 자동으로 조회하여 gemma3, gemma, qwen3, qwen 순으로 우선 선택합니다. WSL → Windows 환경에서는 `ollama-host` 또는 `OLLAMA_HOST` 환경변수로 원격 호스트를 지정할 수 있습니다.

---

## 프로젝트 자동 감지

글로벌 모드(`mindvault global`)에서 하위 프로젝트를 자동 탐색할 때, 다음 14개 마커 파일 중 하나라도 존재하면 프로젝트로 인식합니다:

| 마커 파일 | 생태계 | 마커 파일 | 생태계 |
|-----------|--------|-----------|--------|
| `package.json` | Node.js | `Cargo.toml` | Rust |
| `pyproject.toml` | Python | `go.mod` | Go |
| `setup.py` | Python | `pubspec.yaml` | Flutter/Dart |
| `build.gradle` | Java/Kotlin | `build.gradle.kts` | Kotlin |
| `Podfile` | iOS/macOS | `Gemfile` | Ruby |
| `composer.json` | PHP | `CMakeLists.txt` | C/C++ |
| `Makefile` | 범용 | `CLAUDE.md` | Claude Code |

---

## 크로스 플랫폼 데몬

`mindvault install`을 실행하면 데몬이 자동 등록됩니다. `mindvault global <root> --daemon`으로도 등록할 수 있습니다. OS별 네이티브 서비스 매니저를 사용해 5분마다 변경 사항을 자동 감지하고 업데이트합니다.

| OS | 서비스 매니저 | 비고 |
|----|-------------|------|
| **macOS** | launchd (LaunchAgent) | 로그인 시 자동 시작 |
| **Windows** | Task Scheduler | 로그온 트리거 |
| **Linux** | systemd user service | `--user` 모드 |

```bash
# 데몬 상태 확인
mindvault daemon status

# 데몬 중지
mindvault daemon stop

# 데몬 로그 확인
mindvault daemon log
```

---

## 캐시 & Incremental 업데이트

MindVault는 **SHA256 해시 기반 incremental 캐시**를 사용합니다. 파일이 변경되지 않았으면 재처리하지 않습니다.

- Git post-commit hook이 커밋 시 `mindvault update` 자동 실행
- 변경된 파일만 재추출 → 그래프/위키/인덱스 갱신
- `mindvault watch`로 실시간 감시도 가능 (polling 기반)

---

## Auto-Context Hook (세션 연속성의 핵심)

MindVault의 가장 중요한 기능입니다. `mindvault install` 시 **시스템 레벨 hook**이 설치되어, 사용자가 질문할 때마다 AI가 **자동으로** MindVault를 참조합니다.

```
사용자: "텔레그램 봇 영상에 달린 댓글 어떻게 답해?"
  ↓ (시스템이 자동 실행 — AI의 선택이 아님)
  mindvault query "텔레그램 봇 영상에 달린 댓글 어떻게 답해?" --global
  ↓
  <mindvault-context> 검색결과 + 그래프 + 위키 </mindvault-context>
  ↓
AI: 이미 맥락을 받았으므로 정확한 답변
```

- 10자 미만 짧은 메시지("ㅇㅇ", "해")는 자동 skip
- 5초 timeout으로 응답 지연 없음
- `/` 로 시작하는 skill 명령어도 skip

이 hook이 없으면 AI는 CLAUDE.md의 지시를 "자발적으로" 따라야 하는데, 가끔 무시합니다. Hook은 **시스템이 강제**하므로 AI가 까먹을 수 없습니다.

---

## 메모리 통합

글로벌 빌드(`mindvault global`) 시 Claude Code의 `~/.claude/projects/*/memory/*.md` 파일도 자동으로 검색 인덱스에 포함됩니다. 코드 분석 결과와 프로젝트 메모리가 **하나의 검색 인덱스**로 통합되어, 정보가 어디에 있든 한번에 찾을 수 있습니다.

```
검색: "텔레그램 봇"
  → 코드 분석 결과 (tg_notify.sh 관련 노드)
  → MEMORY.md (커스텀 봇 결정 기록)
  → 위키 페이지 (TTS 파이프라인 연결 관계)
  = 모든 소스 통합
```

---

## 점진적 지식 축적 (Karpathy LLM Wiki 패턴)

[Andrej Karpathy의 LLM Wiki 패턴](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)에서 영감을 받아, MindVault의 위키는 **시간이 지날수록 풍부해집니다.**

### 기존 도구와의 차이

| | 기존 방식 | MindVault |
|---|---|---|
| **위키 생성** | 매번 전체 재생성 | 변경된 부분만 업데이트, 기존 내용 보존 |
| **사용자 메모** | 재생성 시 삭제됨 | `<!-- user-notes -->` 영역은 영구 보존 |
| **외부 자료** | 별도 관리 | 기존 커뮤니티에 자동 분류/병합 |
| **질의 기록** | 사라짐 | `wiki/queries/`에 축적, 검색 가능 |
| **모순 탐지** | 없음 | 3단계 자동 판단 (아래 참고) |

### 지식이 축적되는 흐름

```
1일차: mindvault ingest . → 코드 분석 → 위키 30페이지 생성
        ↓
2일차: 코드 수정 → 데몬이 자동 감지 → 변경된 3페이지만 업데이트
        ↓
3일차: mindvault ingest paper.pdf → 기존 "인증" 커뮤니티에 자동 병합
        ↓
4일차: mindvault query "인증 흐름" --save → 답변이 wiki/queries/에 저장
        ↓
  ...위키가 점점 풍부해짐. 사용자 메모도 보존.
```

### 상호참조

모든 위키 페이지는 `_concepts.json` 인덱스로 연결됩니다. 새 자료가 추가되면 관련 기존 페이지에 자동 백링크가 생성되어, Obsidian에서 Graph View로 전체 지식 구조를 시각화할 수 있습니다.

### 모순 탐지

위키에 같은 개념이 여러 페이지에 등장할 때, `mindvault lint`가 자동으로 모순을 탐지합니다. 사용자 환경에 따라 3단계로 동작합니다:

| 환경 | 모순 판단 방식 | 정확도 |
|---|---|---|
| **로컬 LLM 있음** (Gemma/Ollama) | LLM이 두 설명이 모순인지 직접 판단 | 높음 |
| **구독형 AI에서 실행** (`/mindvault lint`) | Claude/Cursor가 직접 판단 | 높음 |
| **둘 다 없음** | 문자열 비교로 의심 모순 보고 | 기본 |

- 로컬 LLM은 무료이므로 동의 없이 바로 사용합니다
- API 키는 lint에서 절대 사용하지 않습니다 (비용 발생 방지)
- 문자열 비교만으로도 "같은 개념, 다른 설명"은 탐지 가능합니다

---

## 사용 예시

### 새 프로젝트에 MindVault 적용

```bash
cd my-project
pip install mindvault-ai
mindvault install          # AI 도구 연동 + Git hook
mindvault ingest .         # 전체 빌드
mindvault status           # 결과 확인
open mindvault-out/graph.html  # 브라우저에서 그래프 시각화
```

### 외부 자료 수집

```bash
# 파일 수집
mindvault ingest docs/architecture.pdf

# URL 수집
mindvault ingest https://example.com/api-docs

# 디렉토리 일괄 수집
mindvault ingest ./references/
```

### 글로벌 모드 (여러 프로젝트 통합)

```bash
# 하위 프로젝트 자동 탐색
mindvault global ~/projects --discover

# 전체 빌드
mindvault global ~/projects

# 빌드 + 데몬 등록 (install에서 이미 등록된 경우 불필요)
mindvault global ~/projects --daemon

# 크로스 프로젝트 질의
mindvault query "어떤 프로젝트에서 인증 모듈을 사용하나?" --global
```

### 위키 정합성 검사

```bash
mindvault lint
# 위키 페이지의 [[wikilinks]] 유효성 검사
# 그래프의 고아 노드, 순환 참조 탐지
# God Node (과도한 연결) 경고
```

---

## 의존성

| 패키지 | 용도 |
|--------|------|
| `networkx` | 그래프 연산, 커뮤니티 탐지 |
| `tree-sitter` >= 0.23.0 | AST 파싱 엔진 |
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

## 영감을 준 프로젝트

- [Andrej Karpathy의 LLM Wiki 패턴](https://x.com/karpathy) — 코드를 위키로 변환하여 LLM 컨텍스트 효율화
- [graphify](https://github.com/safishamshi/graphify) — 코드베이스 지식 그래프 생성
- [llm-wiki-compiler](https://github.com/nicholaschenai/llm-wiki-compiler) — 지식을 위키로 컴파일
- [qmd](https://github.com/nicholaschenai/qmd) — 로컬 BM25 마크다운 검색

---

## 변경 내역 (v0.5.0)

**구조화 데이터 인덱싱**: `.json`, `.yaml`, `.yml` 파일을 자동으로 검색 인덱스와 지식 그래프에 포함합니다. 프로젝트 산출물(메타데이터, 설정, 빌드 결과)에 담긴 지식이 더 이상 누락되지 않습니다.

- **detect.py**: `data` 카테고리 신설 — `.json`, `.yaml`, `.yml` 파일 자동 감지. 노이즈 파일(`package.json`, `tsconfig.json` 등 30종) 자동 제외
- **extract.py**: `_parse_json()` 추가 — JSON의 `title`/`name`/`description` 필드를 header 노드로, `tags`/`keywords` 배열을 concept 노드로 자동 추출. LLM 불필요, 0 토큰
- **pipeline.py**: `_flatten_json()` + `_index_data_files()` 추가 — JSON 구조를 평탄화하여 BM25 검색 인덱스에 등록. full/incremental 파이프라인 모두 적용
- **compile.py**: data 파일도 그래프 추출 대상에 포함

**실측 효과** (youtube-longform 프로젝트):
- 기존: "L010 MindVault 영상" 검색 → 결과 0건 ❌
- v0.5.0: 검색 인덱스 75 → 145 문서 (+70 data 파일), L010 metadata.json이 상위 결과로 노출 ✅

## 변경 내역 (v0.4.4)

**Key Facts 자동 추출**: 위키 페이지의 Context 섹션이 구조 메타데이터만 출력하던 문제 해결. 이제 소스 파일에서 실제 텍스트 스니펫을 추출하여 `### Key Facts`로 포함합니다.

- **`_find_snippet()` + `_collect_key_facts()`** (wiki.py) — 커뮤니티 노드의 소스 파일에서 label 관련 본문 paragraph를 추출. 헤딩 내 label은 본문으로 점프
- **ingest merge 시 Key Facts 자동 추가** (ingest.py) — `mindvault ingest`로 파일을 수집할 때, 기존 커뮤니티 페이지에 소스 스니펫이 자동 삽입
- **compile 경로 동시 적용** — `generate_wiki()`, `update_wiki()` 모두 Key Facts 포함. full rebuild 시 78페이지 중 45페이지(58%)에 반영
- **실측 A/B 벤치마크 추가** — MindVault ON/OFF 비교: 도구 호출 6→0회, 탐색 토큰 61.8k→0, 응답 55초→즉시

## 변경 내역 (v0.4.3)

**노이즈 필터링 + 토큰 budget**: auto-context 훅이 generic 키워드("업데이트" 등)로 44,000+ 토큰을 주입하던 문제 수정.

- **검색 score cutoff** — BM25 점수 10 미만인 저관련성 결과는 자동 필터링. 노이즈 wiki 페이지가 줄줄이 딸려오는 현상 제거
- **`--budget 5000` 토큰 캡** — 훅이 `mindvault query`에 명시적 budget 전달. wiki context가 5000 토큰을 넘지 않음
- **`head -20` 라인 캡** — hook 출력을 60줄 → 20줄로 제한 (safety net)
- **`_PROMPT_HOOK_SCRIPT` 동기화** — 패키지 내장 hook 스크립트도 budget + head 제한 반영. 다음 `mindvault install`에서 자동 적용

## 변경 내역 (v0.4.2)

**Critical hotfix**: `UserPromptSubmit` auto-context 훅이 **몇 달 동안 조용히 작동하지 않던** 버그 수정. 세션 연속성의 핵심 기능이 실제로는 매 프롬프트마다 즉시 exit 0 하고 아무 컨텍스트도 주입하지 않던 상태였습니다.

근본 원인 세 가지:
1. `$CLAUDE_USER_PROMPT` 환경변수에서 프롬프트를 읽으려고 함 — 이 환경변수는 Claude Code hook 환경에 **존재하지 않음**. 올바른 spec은 stdin으로 JSON payload 전달. 매 실행마다 빈 문자열로 시작해서 길이 체크에서 early exit
2. `timeout` 명령어 사용 — macOS에 기본 탑재 안 됨 (`brew install coreutils`로 `gtimeout` 설치 필요). 리눅스에서는 작동했지만 macOS 사용자는 전원 영향
3. 위 둘이 silent failure 패턴이라 사용자가 버그를 발견할 수 없음

수정:
- **`_PROMPT_HOOK_SCRIPT` 전면 재작성**: stdin JSON 파싱, `gtimeout` fallback, `set -e` 제거, `MINDVAULT_HOOK_VERSION=2` 마커 추가
- **`install_prompt_hook()` auto-upgrade**: 기존 v1 설치 감지해서 자동으로 덮어씀. 이미 v2인 경우 no-op
- **새 CLI 명령 `mindvault doctor`**: hook 상태를 7단계 진단 (파일 존재 / 버전 마커 / 실행 권한 / settings 등록 / CLI PATH / 인덱스 존재 / end-to-end smoke test). 실패 항목이 있으면 exit 1
- **회귀 테스트 17개 추가** (109 → 126): hook 스크립트 템플릿 검증, 자동 업그레이드, end-to-end shell 실행, doctor 진단. `$CLAUDE_USER_PROMPT`가 non-comment 라인에 절대 들어가지 못하도록 lock

업그레이드는 자동입니다: `pip install --upgrade mindvault-ai` 후 `mindvault install`을 한 번 돌리면 깨진 v1 훅이 v2로 교체됩니다. `mindvault doctor`로 상태 확인 가능.

## 변경 내역 (v0.4.1)

**Hotfix**: v0.4.0에서 `export_json`이 `schema_version` 필드를 안 써서, 이미 canonical ID인 그래프가 다음 incremental 실행 시 마이그레이션 루틴에 재진입하며 노드의 `entity_type`이 `entity`로 잘못 분류될 수 있는 버그를 수정했습니다.

- **export.py**: `export_json()`이 `schema_version: 2`를 그래프 메타데이터에 stamp 합니다
- **migrate.py**: canonical 포맷(`::` 2개 이상 포함) 감지 → passthrough. 이미 canonical인 ID는 재작성하지 않고 누락된 `entity_type`만 백필합니다
- **회귀 테스트**: 98 → 109 (+11). canonical passthrough, mixed 레거시+canonical 그래프, `_looks_canonical` 감지, `export_json` schema stamp.

## 변경 내역 (v0.4.0)

**Path-based canonical ID scheme** — 노드 ID가 파일 경로를 기반으로 생성되도록 리팩토링.

### 무엇이 바뀌었나?

기존 ID 스키마는 `{filestem}_{name}` (파일명 + 엔티티명)이었습니다. 이 방식은 같은 파일명이 다른 디렉토리에 있을 때 **ID 충돌**을 일으켰습니다:

```
src/auth/utils.py::def validate() → utils_validate
src/db/utils.py::def validate()   → utils_validate  ← 동일 ID, 노드 병합 ❌
```

v0.4.0부터는 `{rel_path_slug}::{kind}::{local_slug}` 포맷을 사용합니다:

```
src/auth/utils.py::validate → src__auth__utils_py::function::validate
src/db/utils.py::validate   → src__db__utils_py::function::validate   ✅
```

### 마이그레이션

**자동 마이그레이션**: 기존 `graph.json`이 있는 프로젝트에서 `mindvault update` 또는 incremental 갱신을 돌리면, 첫 실행 시 자동으로 canonical 포맷으로 변환합니다 (1~10초, 1회성). 유저 작업 불필요.

**폴백**: 자동 마이그레이션이 실패하면 (`source_file` 필드 누락 등) 콘솔에 다음 지시가 표시됩니다:

```bash
rm -rf mindvault-out
mindvault install
```

### 기타 개선

- **파이프라인 중앙화** — `compile()`과 `run_incremental()`의 중복 로직을 `_finalize_and_export()` 공통 헬퍼로 통합 (Codex Finding #9)
- **회귀 테스트 스위트** — 60 → 98개. canonical ID, 마이그레이션, Codex 지적 사항 전부 커버.
- `entity_type` 필드 추가 — 모든 노드에 `file`/`module`/`class`/`function`/`method`/`header`/`block`/`concept` 분류

### 이전 변경

- **v0.3.2** — tests/ 디렉토리 신설, 60개 회귀 테스트
- **v0.3.1** — Codex 5건 패치 (Unicode 태그, frontmatter line offset, first_header_id 등)
- **v0.3.0** — Obsidian 네이티브 기능 (frontmatter, inline #tags, 재귀 walk, .obsidian/ 제외)

---

## 라이선스

MIT

---

<p align="center">
  <sub>MindVault v0.5.0 | 개발: <a href="https://github.com/etinpres">etinpres</a></sub>
</p>
