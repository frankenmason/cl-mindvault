<p align="center">
  <h1 align="center">MindVault</h1>
  <p align="center">AI 코딩 도구의 "장기 기억" — 코드베이스를 자동으로 지식 그래프 + 위키 + 검색 인덱스로 변환</p>
</p>

<p align="center">
  <a href="https://pypi.org/project/mindvault/"><img src="https://img.shields.io/pypi/v/mindvault?color=blue" alt="PyPI"></a>
  <img src="https://img.shields.io/pypi/pyversions/mindvault" alt="Python 3.10+">
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
pip install mindvault
mindvault install
```

`mindvault install`이 자동으로 수행하는 작업:
- 현재 사용 중인 AI 도구 감지 (7개 지원)
- 각 도구별 통합 설정 파일 생성
- Git post-commit hook 설치 (커밋마다 자동 갱신)
- Claude Code `/mindvault` Skill 등록

### 요구사항

- **Python 3.10+**
- LLM 없이도 AST 기반 코드 구조 분석 동작
- 시맨틱 추출 시 로컬 LLM 또는 API 키 필요 (아래 [LLM 설정](#llm-설정) 참고)

---

## 빠른 시작

### CLI 사용

```bash
# 현재 프로젝트의 지식 베이스 구축
mindvault ingest .

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
소스 파일 / URL / PDF
        |
        v
  [1. Detect]     -- 코드/문서 파일 탐색, 14개 마커 파일로 프로젝트 자동 감지
        |
        v
  [2. Extract]    -- tree-sitter AST → 노드(함수, 클래스, 모듈) + 엣지(호출, 임포트)
        |
        v
  [3. Semantic]   -- LLM으로 Why/How/의도 추출 (선택사항)
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

### 출력 디렉토리 구조

```
mindvault-out/
├── graph.json           # 원본 그래프 데이터 (노드 + 엣지)
├── graph.html           # vis.js 인터랙티브 시각화 (브라우저에서 열기)
├── GRAPH_REPORT.md      # 분석 리포트 (God Nodes, Surprising Connections)
├── wiki/
│   ├── INDEX.md         # 위키 진입점 (전체 커뮤니티 목록)
│   └── *.md             # 커뮤니티별 위키 페이지
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
| `mindvault global <root> --daemon` | 빌드 + 데몬 등록 |

### 데몬 관리

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

질의 토큰 버짓은 `--budget` 옵션으로 조정 가능합니다 (기본값: 2000 토큰).

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
# LLM 엔드포인트 수동 설정
mindvault config llm http://localhost:8080

# API 자동 승인 (매번 묻지 않음)
mindvault config auto-approve true

# 현재 설정 확인
mindvault config show
```

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

`mindvault global <root> --daemon`으로 등록하면, OS별 네이티브 서비스 매니저를 사용해 백그라운드에서 자동 갱신합니다.

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

## 사용 예시

### 새 프로젝트에 MindVault 적용

```bash
cd my-project
pip install mindvault
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

# 빌드 + 데몬 등록 (백그라운드 자동 갱신)
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

## 라이선스

MIT

---

<p align="center">
  <sub>MindVault v0.1.0 | 개발: <a href="https://github.com/etinpres">etinpres</a></sub>
</p>
