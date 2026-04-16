---
name: md2wu
description: "마크다운 문서에서 헤딩 트리 추출 → 토큰 측정(Inclusive/Exclusive) → Source Family 탐지·사용자 승인 → Authority·DocType·Heading Level 분류 → 청크 계획 → Work Unit 패킹 → PRE 매니페스트 생성까지 전체 PRE 파이프라인을 수행한다. TRIGGER when 사용자가 MD 문서의 헤딩 구조 분석·토큰 측정·문서 분류·WU 생성을 요청하거나 /md2wu 호출. DO NOT TRIGGER when PDF→MD 변환(pdf2md), 정의/적용범위/통제용어 추출(TD/APP/CT)."
---

# md2wu — 마크다운 → 헤딩 트리 · 토큰 측정 · 문서 분류 · Work Unit 생성

## 목적

입력된 `.md` 파일(단일/복수/폴더)에서 PRE 파이프라인 전체를 수행한다:

1. **헤딩 추출** — `#` 기반 헤딩 파싱, 계층 트리 구조 생성
2. **토큰 측정** — Inclusive/Exclusive 토큰 수 계산, 가산성 검증
3. **Source Family 탐지** — 토큰 분포 + 헤딩 패턴 → **사용자 승인 후 확정** → 레퍼런스 저장
4. **문서 분류** — Authority, DocType, Heading Level 추출 및 일반화
5. **청크 계획** — 헤딩 경계 기반 재귀 하향식 분할
6. **Work Unit 패킹** — Standalone / Split / Merged WU 생성
7. **PRE 매니페스트** — 다운스트림 단일 진입점 생성

---

## 입력

| # | 항목 | 필수 | 설명 |
|:---:|:---|:---:|:---|
| 1 | 대상 경로 | 필수 | `.md` 파일 경로, 복수 파일 목록, 또는 폴더 경로. `/md2wu path/to/files` |
| 2 | 분류 정의서 | 자동 | `shared/document_classification.md` (`_ko.md`) — 기존 분류 체계 |
| 3 | 프로젝트 정의서 | 자동 | `shared/project_definitions.md` (`_ko.md`) — 식별자·토큰 기준 |
| 4 | 명명 규칙 | 자동 | `shared/naming_convention.md` (`_ko.md`) — 파일명·키 생성 규칙 |
| 5 | 헤딩 프로파일 | 자동 | `.claude/skills/md2wu/heading_profiles.json` — Source Family별 헤딩 정규화 규칙 |

---

## 수행 절차

### Stage 1 — 헤딩 추출, 트리 구조 생성, 문서 메타데이터 추출

1. 대상 `.md` 파일을 줄 단위로 읽는다
2. 마크다운 헤딩(`# ~ ######`)을 파싱한다
   - 코드 블록(`` ``` ``) 내부의 `#`은 무시한다
   - 헤딩 레벨(1~6), 줄 번호, 헤딩 텍스트를 추출한다
3. 헤딩 간 부모-자식 관계를 설정하여 트리 구조를 생성한다
   - 상위 레벨 헤딩이 하위 레벨의 부모가 된다
   - 같은 레벨이 연속되면 형제(sibling)로 처리한다
4. **문서 메타데이터 추출** — 파일을 이미 읽고 있으므로, 파일명과 본문(L1 헤딩, preamble)에서 아래 정보를 함께 추출한다:
   - **문서 제목**: L1 헤딩 텍스트
   - **Revision**: 파일명 및 본문(preamble 영역)에서 추출
   - **Source Family 단서**: 파일 경로 + L1 헤딩에서 수집 → Stage 3 입력으로 전달

**산출물:** 각 파일별 헤딩 리스트 (레벨, 줄번호, 텍스트, 부모 ID) + 문서 메타데이터 (제목, revision, source_family 단서)

> **헤딩 프로파일 참조**: `heading_profiles.json`에 해당 Source Family의 프로파일이 있으면 `heading_recognition`, `normalization_rules`, `exclude_patterns`를 적용한다. 프로파일이 없는 새 Source Family는 범용 마크다운 파싱 후 Stage 3에서 프로파일을 신규 등록한다.

### Stage 2 — 토큰 측정

1. 각 헤딩의 텍스트 범위를 결정한다
   - `Start_Line`: 헤딩 줄
   - `End_Line`: 다음 동일/상위 레벨 헤딩 직전 줄 (또는 파일 끝)
2. **Est_Tokens_Exclusive** 계산: 해당 헤딩 자체 콘텐츠만 (하위 헤딩 범위 제외)
3. **Est_Tokens_Inclusive** 계산: 헤딩 시작~끝 전체 범위
4. **가산성 검증**: `parent.Exclusive + Σ(children.Inclusive) = parent.Inclusive`
5. 토크나이저: `tiktoken` (`cl100k_base`) 우선, 불가 시 `char_approx` (`ceil(chars / 4 × 1.1)`)

**산출물:** `doc-{doc_instance_key}__heading__structure.tsv`

### Stage 3 — Source Family 탐지 및 사용자 승인

1. 추출된 헤딩 패턴을 분석한다:
   - 헤딩 텍스트의 명명 패턴 (Part/Chapter/Section/Regulation/Article 등)
   - 헤딩 레벨별 토큰 분포
   - 문서 경계 패턴
2. 기존 `document_classification.md`의 Source Family 정의와 대조한다
3. **후보를 사용자에게 제시**한다:
   - 매칭된 기존 Source Family 또는 새로운 Source Family 후보
   - 판단 근거 (헤딩 패턴, 토큰 통계)
4. 사용자 응답 처리:
   - `승인` → 확정, `shared/document_classification.md` (`_ko.md`) 갱신 후 Stage 4 진행
   - `수정` → 사용자 피드백 반영 후 재제시
   - `거부` → 해당 파일 건너뛰기

**산출물:** 확정된 Source Family 매핑 + 레퍼런스 갱신 + `heading_profiles.json` 프로파일 추가/갱신 (신규 Source Family 시)

### Stage 4 — Authority · DocType · Heading Level 추출 및 일반화

1. 확정된 Source Family 기준으로:
   - **Authority** 식별: 문서 내 기관명, 파일 경로, 메타데이터에서 추출
   - **DocType** 식별: 문서 유형 패턴 매칭 (UR, UI, SOLAS, Rules 등)
   - **Heading Level** 일반화: Source Family별 계층 명칭 매핑
     ```
     예) IACS: Document → Part → Section → Paragraph → Sub-paragraph
     예) IMO:  Document → Part → Chapter → Regulation → Paragraph
     ```
2. 기존 분류 체계와 비교하여 **신규 항목** 식별
3. `shared/document_classification.md` (`_ko.md`)에 신규 항목 반영
4. 결과를 사용자에게 요약 보고

**산출물:** `corpus__md2wu__classification_result.json` + 레퍼런스 갱신

### Stage 5 — 청크 계획 (Context-Window Chunking)

재귀 하향식 분할로 헤딩 경계에 정렬된 청크를 생성한다.

| 문서 크기 | 전략 |
|:---|:---|
| **≤ Upper Bound (32K)** | 단일 청크 = 1 문서 |
| **> Upper Bound, ≤ 1.5× (48K)** | 단일 청크 예외 허용 (분할하지 않음) |
| **> 1.5× (48K)** | 헤딩 경계에서 분할 |

#### 분할 알고리즘 — L2 원형 유지, 균등 분배

1. L1 헤딩이 1개인 경우(일반적) → L1은 문서 루트이므로 **분할 대상에서 제외**, L2 형제 헤딩만 사용
2. L2 형제 각각을 원자적(atomic) 스팬으로 취급 — **L2 이하 헤딩을 가급적 분할하지 않는다**
3. 목표 청크 수 N = `ceil(total_tokens / chunk_max)`, 목표 토큰 = `total / N`
4. L2 스팬을 순서대로 청크에 배분하되, 목표 토큰에 가까워지면 새 청크를 시작한다 (균등 분배)
5. 분할 결과 16K 미만 청크가 생기면 인접 청크와 병합을 시도한다

#### 오버사이즈 리프 예외

| 옵션 | 조건 | 서브청크 ID |
|:---|:---|:---|
| 단락/목록항목 분할 | 구조적 경계 ≥ 3개, 분할 후 모든 세그먼트 ≤ 상한 | `{ChunkKey}_p{NNN}` |
| 슬라이딩 윈도우 | 단락 분할 실패 시 | `{ChunkKey}_w{NNN}` |
| 사용자 에스컬레이션 | 윈도우가 >20% 분산 또는 구조 모호 | §3.3 이슈 게이트로 보고 |

#### 헤딩 없는 문서 폴백

- ≤ 상한 → 단일 Chunk
- > 상한 → 오버사이즈 리프 예외와 동일 처리, `split_method = "headingless"`

**산출물:** `doc-{doc_instance_key}__heading__chunk_plan.json`

### Stage 6 — Work Unit 패킹

청크를 WU 토큰 범위에 따라 패킹한다.

| 구간 | 토큰 범위 | WU 유형 |
|:---|:---|:---|
| **> 상한** | > 32K | **Split** — 헤딩 경계에서 분할, 인접 청크 탐욕적 병합 |
| **목표 범위** | 16K–32K | **Standalone** — 1 Document = 1 WU |
| **< 하한** | < 16K | **Merge 후보** — 적격 문서와 병합 |

#### 병합 제약 조건

동일한 WU로 병합 가능 조건 (모두 충족):
- 동일 `Authority`, `DocType`, 언어, `grammar_version`, `measure_method`
- 병합 순서: DocumentKey ASCII 사전식
- 합계 토큰 ≤ 상한 (초과 시 현재 WU 닫고 새 WU)
- 마지막 WU가 하한 미만이어도 그대로 수용 (강제 병합 금지)

#### WU_Key 명명 규칙

모든 WU_Key에 `{authority}_{doc_type}_` 접두사를 붙여 파일명만으로 출처를 식별한다.

| WU 유형 | 형식 | 예시 |
|:---|:---|:---|
| Standalone | `{authority}_{doc_type}_{doc_instance_key}` | `iacs_ur_z10_3_rev21_en` |
| Split | `{authority}_{doc_type}_{doc_instance_key}_wu{NNN}` | `iacs_ur_z10_4_rev18_en_wu001` |
| Merged | `{authority}_{doc_type}_merge_{short_hash}` (SHA-256 앞 8자) | `iacs_ur_merge_a3f7c2b1` |

**산출물:** `wu-{wu_key}__pre__meta.json`

### Stage 7 — 이슈 게이트 및 매니페스트 확정

#### 기본 동작: 자동 완료

트리거 없으면 산출물을 `results/`에 직접 기록하고 매니페스트 생성.

#### 이슈 트리거 조건

| 유형 | 조건 | 심각도 |
|:---|:---|:---|
| `oversize_hard` | WU 토큰 > 1.5× 상한 (48K) | HIGH |
| `oversize_exception` | WU 토큰 > 상한 (32K), ≤ 1.5× | INFO |
| `undersized` | WU 토큰 < 하한 (16K), split/standalone만 해당 | LOW |

#### LLM 판정 이력 (`judgments`)

각 스테이지에서 LLM이 애매한 상태에서 결정한 사항을 기록한다. 기계적 임계값 판정(`threshold_issues`)과 별도로 관리.

| 필드 | 설명 |
|:---|:---|
| `stage` | 발생 단계 (S1, S3, S5 등) |
| `severity` | `HIGH` / `MED` / `LOW` |
| `category` | 판정 유형 (doc_key_extraction, revision_extraction, chunk_split_decision, merge_ordering 등) |
| `target` | 대상 파일/문서 |
| `ambiguity` | 애매했던 점 |
| `decision` | 어떻게 결정했는지 + 근거 |
| `risk` | 잘못 판정 시 발생 가능한 위험 |

#### 이슈 발동 시 처리

1. 이슈 보고서 생성: `corpus__md2wu__issue_gate_report.json` (`threshold_issues` + `judgments`)
2. 사용자에게 이슈 목록 제시 및 응답 요청

| 응답 | 조치 | WU `status` |
|:---|:---|:---|
| `proceed` | 이슈 인지, 계속 진행 | `proceeded` |
| `revise` | 임계값 조정 후 재실행 | `revised` → `processed` |
| `abort` | 처리 중단, `skill_md2wu/aborted/`로 격리 | `aborted` |

자동 완료된 WU: `status = processed`

**최종 산출물:** `corpus__pre__manifest.json`

---

## 실행 아키텍처 — 2-Phase 배치 처리

### Phase A — 전량 스캔 (기계적, S1-2)

모든 `.md` 파일에 대해 S1-2(헤딩 추출 + 토큰 측정)를 무조건 전량 실행한다.

- 입력: 폴더 경로
- 출력: `skill_md2wu/queue/sessions/<session_id>/scan_index.json` + TSV 파일
- 락 불필요 — TSV만 생성하고 충돌 위험 없음

`scan_index.json` 스키마:

| 필드 | 타입 | 설명 |
|:---|:---|:---|
| `scan_id` | string | ISO 8601 타임스탬프 |
| `source_dir` | string | 입력 폴더 절대 경로 |
| `files[]` | array | 파일별 `{doc_instance_key, filepath, total_tokens, heading_count, tsv_path}` |
| `total_tokens` | int | 전체 토큰 합계 |
| `total_files` | int | 전체 파일 수 |

### Phase B — 배치 계획

`scan_index.json`을 읽고 **600K 토큰 기준**으로 파일을 배치로 묶는다.

1. 파일을 `doc_key` ASCII 순으로 정렬
2. 순서대로 누적 토큰 합산
3. 누적 > 600K이면 새 배치 시작
4. 배치 계획을 `batch_plan.json`에 기록

### Phase C — 배치 단위 실행 (S3-7)

각 배치를 순차적으로 처리한다.

- S3: Source Family 탐지 — 첫 배치에서만 사용자 승인, 이후 배치는 기확정 SF 재사용
- S4-6: 분류 → 청크 → WU 패킹
- S7: 이슈 게이트 + WU .md 출력 + 매니페스트

---

## 글로벌 락 + 세션 관리

### 디렉토리 구조

```
skill_md2wu/
├── queue/
│   ├── locks/
│   │   └── <corpus_scope>.lock              ← 글로벌 락 (corpus 단위)
│   └── sessions/
│       └── <session_id>/
│           ├── scan_index.json              ← Phase A 결과
│           ├── batch_plan.json              ← Phase B 결과
│           └── batches/
│               └── batch_{NNN}/
│                   └── status.json          ← 배치 상태
├── temp/pre/                                ← 중간 산출물
│   ├── doc-*__heading__structure.tsv
│   ├── doc-*__heading__chunk_plan.json
│   ├── wu-*__pre__meta.json
│   └── corpus-*__md2wu__*.json/.md
├── wu-*__pre__content.md                    ← 최종 WU 콘텐츠
├── corpus-*__pre__manifest.json             ← 최종 매니페스트
└── corpus-*__md2wu__issue_gate_report.json  ← 최종 이슈 보고
```

### 락 메커니즘

| 항목 | 값 |
|:---|:---|
| **락 단위** | `corpus_scope` (예: `iacs_ur_z`) — 같은 문서군 동시 실행 방지 |
| **파일** | `skill_md2wu/queue/locks/<corpus_scope>.lock` |
| **생성** | `open(path, "x")` (POSIX O_CREAT\|O_EXCL, atomic) |
| **내용** | `{"owner":"<session_id>","state":"<state>","claimed_at":"<ISO8601>"}` |
| **상태** | `scanning` → `batching` → `processing` → (unlink 또는 `failed`) |
| **상태 갱신** | atomic rename (`tmp → lock`) |
| **해제** | `os.unlink(lock)` — 모든 배치 완료 후 |
| **stale 임계** | 4시간 (mtime 기준) |
| **실패 시** | `state=failed`로 갱신, 파일 유지, 자동 접수 금지 |

**멀티 세션 분담 (session-queue §6.6)**: 입력에 복수 `corpus_scope`가 존재하는 경우, 락 단위가 corpus이므로 **한 세션은 자기 `session_capacity`(예: 처리할 corpus 개수 또는 누적 토큰 상한) 내에서만 corpus 락을 점유**하고, 초과분 corpus는 락·pending 모두 건드리지 않고 원본 상태로 보존해 다른 세션/계정이 가져갈 수 있게 한다. 같은 corpus의 Phase B 배치는 분할 불가(단일 세션이 corpus 단위로 전체 처리).

### 세션 ID

Claude Code 세션 UUID 사용 (`~/.claude/projects/<project>/<session_id>.jsonl`에서 추출).

---

## 산출물 카탈로그

abort 시 `skill_md2wu/aborted/{doc_instance_key}/`로 격리.
신규 Source Family 발견 시 `shared/document_classification.md` (`_ko.md`) 갱신 (추가만 허용).

### 최종 산출물

저장 경로: `skill_md2wu/`

| # | 산출물 | 파일명 패턴 | 설명 |
|:---:|:---|:---|:---|
| F1 | **WU 콘텐츠** | `wu-{wu_key}__pre__content.md` | 실제 원문 텍스트 (WU별 1개 파일) |
| F2 | **PRE 매니페스트** | `corpus-{authority}_{doc_type}_{series}__pre__manifest.json` | 다운스트림 단일 진입점 (WU 목록·상태·토큰) |
| F3 | **이슈 게이트 보고** | `corpus-{authority}_{doc_type}_{series}__md2wu__issue_gate_report.json` | `threshold_issues` (토큰 초과/미달) + `judgments` (LLM 판정 이력) |

### 중간 산출물

저장 경로: `skill_md2wu/temp/pre/` — 파이프라인 완료 후 삭제 가능

| # | 산출물 | 파일명 패턴 | 설명 |
|:---:|:---|:---|:---|
| T1 | 헤딩 구조 TSV | `doc-{doc_instance_key}__heading__structure.tsv` | 헤딩 트리 + 토큰 측정 |
| T2 | 청크 계획 | `doc-{doc_instance_key}__heading__chunk_plan.json` | 청크 경계·토큰·분할 방식 |
| T3 | Source Family 보고 | `corpus-{authority}_{doc_type}_{series}__md2wu__source_family_report.md` | 탐지 결과 및 승인 이력 |
| T4 | 분류 결과 | `corpus-{authority}_{doc_type}_{series}__md2wu__classification_result.json` | Authority·DocType·Heading Level |
| T5 | WU 메타데이터 | `wu-{wu_key}__pre__meta.json` | WU 구성·토큰·상태 (개별 JSON) |

### 세션 산출물

저장 경로: `skill_md2wu/queue/sessions/<session_id>/`

| # | 산출물 | 파일명 | 설명 |
|:---:|:---|:---|:---|
| S1 | 스캔 인덱스 | `scan_index.json` | Phase A 결과 (전체 파일 토큰 목록) |
| S2 | 배치 계획 | `batch_plan.json` | Phase B 결과 (600K 단위 배치 분할) |
| S3 | 배치 상태 | `batches/batch_{NNN}/status.json` | 배치별 진행 상태 |

---

## TSV 스키마 — 헤딩 구조

```
Heading_ID	Level	Start_Line	End_Line	Title	Parent_ID	Est_Tokens_Inclusive	Est_Tokens_Exclusive
```

| 필드 | 타입 | 설명 |
|:---|:---|:---|
| `Heading_ID` | string | `{DocumentKey}_HD_{NNN}` (3자리 zero-pad) |
| `Level` | int | 마크다운 헤딩 레벨 (1~6) |
| `Start_Line` | int | 헤딩 시작 줄 번호 |
| `End_Line` | int | 헤딩 종료 줄 번호 (다음 동일/상위 레벨 헤딩 직전) |
| `Title` | string | 헤딩 텍스트 (`#` 제외) |
| `Parent_ID` | string | 부모 헤딩 ID (루트면 빈 문자열) |
| `Est_Tokens_Inclusive` | int | 하위 포함 토큰 수 |
| `Est_Tokens_Exclusive` | int | 자체 콘텐츠만 토큰 수 |

---

## 청크 계획 스키마

`doc-{doc_instance_key}__heading__chunk_plan.json` 각 청크 항목:

| 필드 | 타입 | 설명 |
|:---|:---|:---|
| `chunk_key` | string | `{doc_instance_key}_ch{NNN}` |
| `heading_range` | object\|null | `{"first": "<Heading_ID>", "last": "<Heading_ID>"}` |
| `heading_level` | string\|null | 청크 경계 헤딩 수준명 (IACS: Document/Section/Paragraph/Sub-paragraph) |
| `start_line` | int | 시작 줄 (포함) |
| `end_line` | int | 종료 줄 (포함) |
| `est_tokens` | int | 청크 토큰 수 |
| `split_method` | string | `recursive` / `oversize_paragraph` / `oversize_window` / `oversize_preamble` / `headingless` |
| `measure_method` | string | `tiktoken` 또는 `char_approx` |
| `sub_chunks` | array\|null | 오버사이즈 분할 시 서브청크 배열 |

---

## WU 메타데이터 스키마

`wu-{wu_key}__pre__meta.json`:

| 필드 | 타입 | 설명 |
|:---|:---|:---|
| `wu_key` | string | WU_Key |
| `wu_type` | string | `standalone` / `split` / `merged` |
| `authority` | string | 발행 기관 |
| `doc_type` | string | 문서 카테고리 |
| `language` | string | 언어 코드 |
| `grammar_version` | string | 헤딩 문법 버전 |
| `measure_method` | string | `tiktoken` 또는 `char_approx` |
| `constituent_docs[]` | array | 구성 문서 목록 (doc_instance_key, document_key, start_line, end_line, est_tokens, heading_range) |
| `est_tokens_total` | int | WU 전체 토큰 수 |
| `chunk_keys[]` | array | 포함된 ChunkKey 목록 |
| `status` | string | `planned` → `processed` / `proceeded` / `revised` / `aborted` |
| `output_files[]` | array | 생성된 산출물 경로 |
| `created_at` | string | ISO 8601 타임스탬프 |

---

## 에이전트 할당

| 단계 | 할당 | 병렬 전략 |
|:---|:---|:---|
| Stage 1–2 (헤딩 추출 + 토큰 측정) | 파일당 1개 에이전트 | 최대 5개 병렬, 초과 시 배치 |
| Stage 3 (Source Family 승인) | Coordinator 단독 | 사용자 대화 필요 — 순차 |
| Stage 4 (분류 추출) | Coordinator 단독 | 순차 |
| Stage 5–6 (청크 + WU 패킹) | Coordinator 단독 | 순차 |
| Stage 7 (이슈 게이트 + 매니페스트) | Coordinator 단독 | 순차 |

---

## 토큰 임계값 (기본값)

| 파라미터 | 값 | 용도 |
|:---|:---|:---|
| `chunk_max` (Upper Bound) | 32K | 청크 분할 상한 |
| `chunk_exception` | 48K (1.5×) | 이 이하이면 분할하지 않고 예외 허용 |
| `wu_range` | 16K–32K | Standalone WU 목표 범위 |
| `wu_lower` | 16K | Merge 후보 기준 |

> 임계값은 `shared/thresholds.yaml` 정본을 참조한다. 사용자가 `revise` 시 조정 가능.

---

## 사용자 승인 프로토콜 (Stage 3)

```
## Source Family 탐지 결과

### 파일: {파일명}
- **후보 Source Family**: {후보명}
- **판단 근거**:
  - 헤딩 패턴: {Part/Chapter/Section 등 감지된 패턴}
  - 토큰 분포: 평균 {N}K, 최대 {N}K
  - 기존 매칭: {기존 Source Family와의 유사도}
- **조치**: [승인 / 수정 / 거부]
```

---

## 완료 조건

| # | 조건 |
|:---:|:---|
| 1 | 모든 대상 문서의 `__heading__structure.tsv` 생성 완료 |
| 2 | 가산성 검증 통과 (Error 0건) |
| 3 | Source Family 사용자 승인 완료, 레퍼런스 갱신 |
| 4 | Authority·DocType·Heading Level 추출 및 레퍼런스 갱신 |
| 5 | 청크 계획 + WU 패킹 계획 생성 |
| 6 | 이슈 게이트 처리 완료 (트리거 미발동 또는 사용자 응답 처리) |
| 7 | `corpus__pre__manifest.json` 생성 |
| 8 | `corpus__md2wu__stage_log.md` 생성 (스테이지별 이슈·결정 기록) |

---

## 스테이지 로그 (`corpus__md2wu__stage_log.md`)

각 스테이지 완료 시 주요 이슈·결정·주의사항을 누적 기록한다. 여러 문서군을 순차 처리할 때 작업 간 비교·추적용.

### 필수 포함 항목

| 스테이지 | 기록 항목 |
|:---|:---|
| S1–2 | 토크나이저 선택, 병렬 배치 수, 가산성 검증 결과, 네이밍 이슈 |
| S3 | Source Family 후보·판단 근거·승인 결과, 레퍼런스 갱신 여부 |
| S4 | Authority·DocType·Heading Level, 신규 항목 유무 |
| S5 | 문서 크기 분포 (단일/예외/분할), 분할 결정 상세 |
| S6 | WU 유형별 수량, Merge WU 구성 상세, 하한 미달 WU 처리 |
| S7 | 이슈 목록 (유형·심각도·처리), 최종 WU 수·토큰 총합 |

### 형식

```markdown
# md2wu Stage Log — {문서군 이름}

| 항목 | 값 |
|:---|:---|
| **대상** | `{경로}` ({N} files) |
| **실행일** | {날짜} |
| **총 토큰** | {N} |
| **최종 WU 수** | {N} (split: {n}, standalone: {n}, merged: {n}) |

## Stage 1-2: 헤딩 추출 + 토큰 측정
### 주요 결정
### 이슈 및 해결
(이슈 | 심각도 | 해결 테이블)

## Stage 3: Source Family 탐지
...이하 스테이지별 반복...
```

---

## 제약 사항

- `.md` 파일만 처리. PDF/HTML은 사전 변환 필요 (pdf2md 등)
- 코드 블록 내부의 `#`은 헤딩이 아님
- 헤딩 없는 파일: 단일 Chunk로 처리 (Stage 5 폴백)
- `document_classification.md` 갱신은 추가만 허용 (기존 항목 삭제 금지)
- Split WU 조각은 다른 문서와 병합 불가
