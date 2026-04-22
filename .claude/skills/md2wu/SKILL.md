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

## 용어 (Terminology)

본 스킬은 [queue-lock](../queue-lock/SKILL.md)의 규약을 채택한다. 키 간 포함 관계는 다음과 같다.

| 용어 | 정의 | 예시 | 역할 |
|:---|:---|:---|:---|
| `item_id` | **락·배치의 최소 단위**. 1 MD 파일 = 1 item. `doc_instance_key`와 동일 값이며, 이미 `{authority}_{doc_type}_` 접두사를 포함한다. | `iacs_ur_z10_3_rev21_en` (`iacs_ur_` = authority+doc_type, `z10_3_rev21_en` = 문서 고유부) | queue-lock `<item_id>` |
| `doc_instance_key` | item 식별자의 정본. `item_id`와 동일 값 (접두사 포함). | 위와 동일 | 파일 고유 ID |
| `source_family` | 헤딩 패턴·문서 구조 규칙을 공유하는 분류 단위 (Stage 3에서 확정). | `iacs_ur`, `iacs_ui`, `imo_solas` | 배치 그룹화 1차 키 |
| `series` | 같은 `source_family` 내부에서 번호 연속성을 갖는 문서 묶음. | `Z10` (Z10.1~Z10.11), `E26`, `S-series` | 배치 그룹화 2차 키 |
| `series_order` | series 내부 문서 정렬용 키 (서브번호·revision 순). | `Z10.1 rev21 < Z10.2 rev18 < Z10.3` | 병합·배치 내부 정렬 |
| `corpus_scope` | 보고·집계용 상위 범위 키. **락 단위가 아님**. | `iacs_ur_z` (UR 중 Z 시리즈 전체) | manifest·통계 집계 |
| `document_key` | revision 제거된 논리 문서 키(필요 시 별도 필드). | `iacs_ur_z10_3` | WU 내부 참조용 |

- `doc_key`라는 약칭은 사용하지 않는다.
- `item_id`는 파일명 안전 문자(`[A-Za-z0-9._-]`)만 사용한다.
- `source_family` → `series` → `item`은 상위→하위 포함 관계이며, 락은 **item 단위**로만 건다.
- `series_group`은 `series`의 이전 명칭이며 본 문서는 `series`로 통일한다. 코드·스키마에 남은 `series_group` 식별자는 호환을 위해 유지되며 별도 리팩토링 과제로 추적한다.

---

## 입력

| # | 항목 | 필수 | 설명 |
|:---:|:---|:---:|:---|
| 1 | 대상 경로 | 필수 | `.md` 파일 경로, 복수 파일 목록, 또는 폴더 경로. `/md2wu path/to/files` |
| 2 | 분류 정의서 | 선택(사용자 제공) | `shared/document_classification.md` (`_ko.md`) — 기존 분류 체계. 저장소에 존재할 때만 로드한다. |
| 3 | 프로젝트 정의서 | 선택(사용자 제공) | `shared/project_definitions.md` (`_ko.md`) — 식별자·토큰 기준. 저장소에 존재할 때만 로드한다. |
| 4 | 명명 규칙 | 선택(사용자 제공) | `shared/naming_convention.md` (`_ko.md`) — 파일명·키 생성 규칙. 저장소에 존재할 때만 로드한다. |
| 5 | 헤딩 프로파일 | 자동 | `.claude/skills/md2wu/heading_profiles.json` — Source Family별 헤딩 정규화 규칙 |

> 위 2~4번 파일은 모두 **선택 입력**이다. 저장소에 해당 파일이 없으면 스킬은 그 참조를 **빈 값으로 간주하고 진행**하며, 기존 분류/식별자/명명 규칙이 없을 때는 Stage 3·4에서 사용자에게 직접 입력을 요청하거나 세션 내 메모리로만 결정을 기록한다. 새 파일을 자동 생성하지 않는다.

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

**산출물:** `parts/doc_parts.json`의 `items[<item_id>].headings` 항목 (세션 내 모든 item이 단일 파일에 통합 저장).

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
   - `승인` → 확정. `shared/document_classification.md` (`_ko.md`) 파일이 **제공된 경우에만 갱신**하고, 없으면 세션 내 메모리(스테이지 로그·매니페스트)에만 기록한 뒤 Stage 4 진행.
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
3. `shared/document_classification.md` (`_ko.md`)가 **제공된 경우에만** 신규 항목을 append(추가만 허용)한다. 파일이 없으면 갱신을 건너뛰고 세션 내 메모리(스테이지 로그·매니페스트)에만 기록한다.
4. 결과를 사용자에게 요약 보고

**산출물:** `corpus-{scope}__md2wu__classification_result.json` + 레퍼런스 갱신 — 세션 로컬 중간본은 scope 생략 허용, publishing 시 scope 포함 파일명으로 전역 승격.

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
| 사용자 에스컬레이션 | 윈도우가 >20% 분산 또는 구조 모호 | Stage 7 이슈 게이트로 보고 |

#### 헤딩 없는 문서 폴백

- ≤ 상한 → 단일 Chunk
- > 상한 → 오버사이즈 리프 예외와 동일 처리, `split_method = "headingless"`

**산출물:** `parts/doc_parts.json`의 `items[<item_id>].chunk_plan` 항목 (Stage 1 결과물과 같은 단일 파일에 병합 저장; Phase C에서 본 세션이 claim한 item만 채워진다).

### Stage 6 — Work Unit 패킹

청크를 WU 토큰 범위에 따라 패킹한다.

| 구간 | 토큰 범위 | WU 유형 |
|:---|:---|:---|
| **> 상한** | > 32K | **Split** — 헤딩 경계에서 분할, 인접 청크 탐욕적 병합 |
| **목표 범위** | 16K–32K | **Standalone** — 1 Document = 1 WU |
| **< 하한** | < 16K | **Merge 후보** — 적격 문서와 병합 |

#### 병합 제약 조건

동일한 WU로 병합 가능 조건 (모두 충족):
- 동일 `source_family`, 동일 `series`(또는 series 없음)
- 동일 `Authority`, `DocType`, 언어, `grammar_version`, `measure_method`
- 병합 순서: `series_order` 우선, 동률 시 `doc_instance_key` 보조 정렬
- 합계 토큰 ≤ 상한 (초과 시 현재 WU 닫고 새 WU)
- 마지막 WU가 하한 미만이어도 그대로 수용 (강제 병합 금지)

#### WU_Key 명명 규칙

`item_id`(=`doc_instance_key`)는 이미 `{authority}_{doc_type}_` 접두사를 포함하므로 WU_Key 구성 시 접두사를 **추가하지 않는다** (이중 접두사 방지). Merged WU만 원본 item이 없으므로 접두사를 직접 부여한다.

| WU 유형 | 형식 | 예시 |
|:---|:---|:---|
| Standalone | `{item_id}` | `iacs_ur_z10_3_rev21_en` |
| Split | `{item_id}_wu{NNN}` | `iacs_ur_z10_4_rev18_en_wu001` |
| Merged | `{authority}_{doc_type}_merge_{short_hash}` (SHA-256 앞 8자) | `iacs_ur_merge_a3f7c2b1` |

**산출물:** WU 메타는 별도 파일을 생성하지 않고 곧바로 세션 로컬 매니페스트 `corpus-{scope}__pre__manifest.json`의 `work_units[]`에 기록한다 (단일 정본 — §"PRE 매니페스트 스키마" 참조).

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
| `category` | 판정 유형 (item_id_extraction, revision_extraction, source_family_assign, chunk_split_decision, merge_ordering 등) |
| `target` | 대상 파일/문서 |
| `ambiguity` | 애매했던 점 |
| `decision` | 어떻게 결정했는지 + 근거 |
| `risk` | 잘못 판정 시 발생 가능한 위험 |

#### 이슈 발동 시 처리

1. 이슈 보고서 생성: `corpus-{scope}__md2wu__issue_gate_report.json` (`threshold_issues` + `judgments`) — `{scope}` = `{authority}_{doc_type}_{series}` (예: `iacs_ur_z`). 세션 로컬 중간본은 scope 생략 허용.
2. 사용자에게 이슈 목록 제시 및 응답 요청

| 응답 | 조치 | WU `status` |
|:---|:---|:---|
| `proceed` | 이슈 인지, 계속 진행 | `proceeded` |
| `revise` | 임계값 조정 후 재실행 | `revised` → `processed` |
| `abort` | 처리 중단, `skill_md2wu/aborted/`로 격리 | `aborted` |

자동 완료된 WU: `status = processed`

**최종 산출물:** `corpus-{scope}__pre__manifest.json` — `{scope}` = `{authority}_{doc_type}_{series}`. 세션 로컬 중간본은 scope 생략 허용, publishing 시 scope 포함 파일명으로 전역 승격.

---

## 실행 아키텍처 — 3-Phase 배치 처리 (Phase A/B/C)

### Phase A — 전량 스캔 (기계적, S1-2)

모든 `.md` 파일에 대해 S1-2(헤딩 추출 + 토큰 측정)를 무조건 전량 실행한다.

- 입력: 폴더 경로
- 출력: `skill_md2wu/queue/sessions/<session_id>/scan/scan_index.json` + `parts/doc_parts.json` (세션 내 전체 item의 `headings`를 단일 파일로 통합 저장)
- 락 불필요 — JSON 1개만 생성하고 충돌 위험 없음

`scan_index.json` 스키마:

| 필드 | 타입 | 설명 |
|:---|:---|:---|
| `scan_id` | string | ISO 8601 타임스탬프 |
| `source_dir` | string | 입력 폴더 절대 경로 |
| `files[]` | array | 파일별 `{item_id, filepath, cost_tokens, heading_count, source_family, series, series_order, revision}` (`item_id` = `doc_instance_key`; 헤딩 세부 데이터는 `parts/doc_parts.json`의 `items[item_id]` 참조) |
| `total_tokens` | int | 전체 토큰 합계 |
| `total_files` | int | 전체 파일 수 |

### Phase B — 배치 계획 (Source Family 우선 · Series 연속성 · NFD)

`scan_index.json`의 item 목록을 받아 **`batch_capacity` 이하**로 배치를 구성한다. 기본값은 `600K` 토큰(사용자/메모리 오버라이드 가능; 200K 등).

#### B-0. 스킵 판정 ([queue-lock §5](../queue-lock/SKILL.md))
1. 전역 경로의 `merge_index.json`을 로드한다 (없으면 초기 실행으로 간주, 스킵 없음).
2. `merge_index.json`의 `corpora.{scope}.item_to_wu[item_id]`가 존재하고, 매핑이 가리키는 **모든** `wu_key`에 대해 전역 `wu-{wu_key}__pre__content.md` 파일이 존재하며 0바이트가 아닐 때 본 실행에서 제외한다 (하나라도 누락이면 미처리로 간주). 세션 로컬 매니페스트(T2)는 스킵 판정에 사용하지 않는다 — 전역 SSOT는 `merge_index.json` 하나다.
3. `merge_index.json`은 Merged WU·Split WU 포함 모든 WU 유형에 대해 `item_id → [wu_keys]` (list) 관계를 명시한다. Merged WU(복수 item → 단일 WU), Split WU(단일 item → 복수 WU) 모두 정확히 감지된다. 하위 호환: 레거시 `item_id → wu_key` (string) 매핑도 단일 원소 리스트로 해석한다.
4. 스킵된 item의 락 파일은 건드리지 않는다 (다른 세션이 이미 보유 중일 수 있음).

#### B-1. Source Family 사전 확정
Phase B 진입 전에 Stage 1의 메타데이터로 **모든 item에 provisional `source_family`를 할당**한다. 미확정 family가 있으면 Stage 3 승인 절차를 **먼저** 수행한 뒤 Phase B로 진입한다 (배치 내 family 혼합 방지).

#### B-2. 그룹화 및 정렬 (우선순위)
1. **1차 그룹**: `source_family` — 서로 다른 family는 같은 배치에 넣지 않는다.
2. **2차 그룹**: `series` — 같은 family 내부에서 series별로 묶는다.
3. **series 내부 정렬**: `series_order` 오름차순 (연속성 유지). series 없는 item은 `doc_instance_key` 보조 정렬.
4. **그룹 간 배치 선택 우선순위**: 큰 그룹(합산 `cost_tokens` 큰 순)부터 배치화 ([queue-lock §6.3](../queue-lock/SKILL.md) 큰 아이템 우선 원칙).

#### B-3. NFD 패킹 ([queue-lock §6.2](../queue-lock/SKILL.md))
각 `(source_family, series)` 단위로 Next-Fit Decreasing을 적용:
1. 현재 배치 합 + `item.cost_tokens` ≤ `batch_capacity` → 현재 배치에 추가.
2. 초과 시 현재 배치를 닫고 새 배치를 연다.
3. **series 연속성 우선**: 예산에 여유가 있는 한 같은 series는 같은 배치에 유지. 예산을 초과하는 시점에만 series 경계에서 분리한다.
4. 단일 item이 `batch_capacity`를 초과하면 [queue-lock §6.1](../queue-lock/SKILL.md) 규칙에 따라 사용자에게 물리 분할을 요청하고 이번 실행에서 제외한다.

#### B-4. 세션 점유 (multi-session handoff, [queue-lock §6.6](../queue-lock/SKILL.md))
- `session_capacity` 기본값은 `batch_capacity`와 동일 (**한 세션 = 1 배치**).
- 첫 배치(우선순위 가장 높은 family·series)만 락 claim하고 나머지 배치는 **락·pending 모두 건드리지 않고** 보존한다.
- 보존된 배치는 `batch_plan.json`에 기록하되 `status: "reserved_for_other_session"`으로 표기한다.
- 단, 이 필드는 **세션 로컬 기록(관찰성)용**이며, 다른 세션과의 실제 조율은 글로벌 락(`EEXIST`)과 산출물 스킵 판정(§5)으로만 이루어진다.
- 다른 세션이 기동되면 §5 스킵 판정 후 남은 item을 같은 방식으로 가져간다.
- **사용자 알림 (필수)**: 이번 세션이 claim한 배치의 모든 item에 대해 락 점유(`O_CREAT|O_EXCL` + 초기 JSON 기록, [queue-lock §3.1](../queue-lock/SKILL.md))가 완료되면 **사용자에게 즉시 "락 작업이 완료되었음"을 보고**한다. 보고에는 다음을 포함한다 — `batch_id`, `source_family`·`series_keys`, 점유한 item 수·`item_id` 목록(많으면 요약), 락 파일 경로 템플릿(`skill_md2wu/queue/locks/<item_id>.lock`), `session_id`, 점유 시각, `reserved_for_other_session`으로 남겨둔 배치 수. 이 알림 이후에 Phase C(S3-7) 실행을 시작한다.

#### B-5. 산출물
`batch_plan.json`에 기록:

| 필드 | 설명 |
|:---|:---|
| `batch_id` | `B{NNN}` 3자리 zero-pad |
| `source_family` | 배치의 단일 family |
| `series_keys[]` | 배치에 포함된 series 키 목록 |
| `items[]` | `{item_id, cost_tokens, series_order, filepath}` |
| `cost_total` | 배치 합산 토큰 |
| `status` | `claimed` / `reserved_for_other_session` |

### Phase C — 배치 단위 실행 (S3-7)

이번 세션이 claim한 단일 배치를 순차적으로 처리한다.

- S3: Source Family — 이미 Phase B-1에서 확정되었으므로 본 단계는 기확정 SF 재사용 (신규 후보 추가 발생 시 사용자 재승인).
- S4-6: 분류 → 청크 → WU 패킹.
- S7: 이슈 게이트 + WU .md 출력 + 매니페스트.

---

## queue-lock §9 통합 선언

본 스킬은 [queue-lock](../queue-lock/SKILL.md)를 채택한다. 공통 규약(작업 파일 스키마 기본 형태, `cost` 단위 원칙, `<terminal_phase>` 개념, §7 정리 경로 템플릿, 크래시 복구, 패킹 전략 기본)은 [queue-lock §3·§6·§7·§9](../queue-lock/SKILL.md)를 그대로 따르며, 아래 표에는 **md2wu 고유 값**만 선언한다.

| 항목 | 값 |
|:---|:---|
| `workroot` | `skill_md2wu/` (프로젝트 루트 기준) |
| `item_id` | `doc_instance_key` — **1 MD 파일 = 1 item** |
| `cost` 단위 | 토큰 수 (`cost_tokens`, tiktoken `cl100k_base` 또는 `char_approx` 폴백) |
| `batch_capacity` | **기본 600K 토큰** — 사용자/메모리(feedback) 오버라이드 가능 (예: 200K) |
| `session_capacity` | `batch_capacity`와 동일 (한 세션 = 1 배치). 락 점유 타이밍 = Phase B-4 직후 |
| 스킵 판정 | `merge_index.json`의 `corpora.{scope}.item_to_wu[item_id]` 키 존재 + 매핑된 **모든** `wu_key`에 대해 `wu-{wu_key}__pre__content.md` 존재·비영 (Merged/Split WU 포함 모든 WU 유형 일관 판정; 레거시 string 매핑도 허용). 세션 로컬 매니페스트(T2)는 스킵 판정에 참여하지 않는다. |
| `<caller_dirs>` | `scan/`, `plans/`, `parts/`, `out/`, `assets/`, `logs/` (모두 `sessions/<session_id>/` 하위) |
| 보고 채널 | 표준 사용자 보고 + `agent_report.md` (모호 판정·처리 결과 append) |

### 디렉토리 구조

```
skill_md2wu/
├── queue/
│   ├── locks/
│   │   └── <item_id>.lock                   ← 글로벌 락 (item = 1 MD 파일 단위)
│   └── sessions/
│       └── <session_id>/                    ← 세션 로컬 (격리)
│           ├── pending/<item_id>/task.json
│           ├── working/<item_id>/
│           ├── done/<item_id>/
│           ├── failed/<item_id>/
│           ├── scan/scan_index.json         ← Phase A 결과
│           ├── plans/batch_plan.json        ← Phase B 결과
│           ├── parts/doc_parts.json        ← 세션 내 전체 item의 headings + chunk_plan 통합 JSON
│           ├── out/<item_id>__*.json        ← 중간 WU 메타·분류 결과
│           ├── assets/<item_id>/            ← 아이템별 보조 산출물
│           └── logs/                        ← 배치·이슈 로그
├── wu-{wu_key}__pre__content.md             ← 최종 WU 콘텐츠 (publishing 이후 전역, {wu_key}는 standalone/split/merged 규칙에 따름)
└── merge_index.json                          ← 전 corpus 통합 머지/분리 맵 (F2, 전역 유일 JSON)
```

중간 산출물은 모두 `sessions/<session_id>/<caller_dirs>/` 하위에 두고, `<terminal_phase> = publishing` 진입 시에만 최종 산출물(`wu-*`, `corpus-*__pre__manifest.json`)을 전역 경로로 원자 `mv` 한다.

### 락 메커니즘

락 프로토콜 상세(원자 생성·JSON 본문 스키마·atomic replace 갱신·해제·stale·실패 처리)는 [queue-lock §3](../queue-lock/SKILL.md)을 그대로 따른다. md2wu 고유 값은 아래 3항목.

| 항목 | 값 |
|:---|:---|
| **락 단위** | `item_id`(=`doc_instance_key`) — **1 MD 파일 = 1 락** |
| **파일 경로** | `skill_md2wu/queue/locks/<item_id>.lock` (단일 정규 파일) |
| **`<terminal_phase>`** | `publishing` — queue-lock §1 정의에 따른 종결 직전 단계명. 진입 시 §"전역 발행 정책"의 두 산출물(`wu-*__pre__content.md`, `merge_index.json`)을 전역 경로로 원자 승격한 뒤 락을 `unlink` 한다. |
| **락 상태 시퀀스** | `pending → working → publishing → (unlink)` 또는 `→ failed`. 모든 전이는 queue-lock §3.2 atomic replace 규약을 따른다. |
| **큐 상태 전이** | `pending/<item_id>/ → working/<item_id>/ → done/<item_id>/` 또는 `→ failed/<item_id>/`. 모든 이동은 `mv`(POSIX `rename(2)`) 단일 호출로 수행 (queue-lock §4). |

### 멀티 세션 분담

입력 범위에 여러 source_family·series가 있더라도, **한 세션은 Phase B에서 선택된 단일 배치의 item들에만 락을 건다**. 나머지 item은 락·pending 모두 건드리지 않고 원본 상태로 보존되어 다른 세션/계정이 §5 스킵 판정 후 가져갈 수 있다. 락은 item 단위이므로 `EEXIST`로 자동 충돌 회피된다.

### 세션 ID

Claude Code 세션 UUID 사용 (`~/.claude/projects/<project>/<session_id>.jsonl`에서 추출).

---

## 산출물 카탈로그

abort 시 `skill_md2wu/aborted/{doc_instance_key}/`로 격리.
신규 Source Family 발견 시 `shared/document_classification.md` (`_ko.md`)가 **제공된 경우에만 갱신**(추가만 허용). 파일이 없으면 갱신을 생략하고 세션 내 메모리(스테이지 로그·매니페스트)에만 기록한다.

### 전역 발행 정책 (사용자 지침)

`skill_md2wu/` 루트(전역)에는 **아래 두 종류 파일만** 남긴다. 다른 모든 산출물(매니페스트·이슈 게이트·스테이지 로그 등)은 세션 로컬에만 존재하며 `<terminal_phase> = publishing` 완료 후 §7 정리 단계에서 삭제한다.

1. `wu-{wu_key}__pre__content.md` — WU별 원문 콘텐츠
2. `merge_index.json` — **어떤 item들이 머지되고 어떤 item이 분리되었는지**를 알 수 있는 단일 정본 JSON. 전 corpus 통합(`corpora.{scope}.item_to_wu`) 구조로 한 파일에 모은다. Phase B-0 스킵 판정의 정본 근거이기도 하다.

**이유**: 사용자가 최종 발행 디렉터리의 시각적 잡음을 최소화하고 "머지/분리 맵"만 SSOT로 남기길 원함. 매니페스트·이슈게이트·스테이지 로그는 세션 산출물(감사/디버깅용)에 속하며 발행 대상이 아님.

### 최종 산출물 (전역)

저장 경로: `skill_md2wu/`

| # | 산출물 | 파일명 | 설명 |
|:---:|:---|:---|:---|
| F1 | **WU 콘텐츠** | `wu-{wu_key}__pre__content.md` | 실제 원문 텍스트 (WU별 1개 파일) |
| F2 | **머지/분리 인덱스 (통합)** | `merge_index.json` | 전체 corpus의 `item_id → [wu_keys]` 매핑을 한 파일에 담는다. 스키마: `{generated_at, corpora: {<scope>: {item_to_wu: {<item_id>: [<wu_key>, ...]}}}}`. Merged WU(여러 item → 단일 wu_key) 및 Split WU(단일 item → 복수 wu_key) 모두 list 값으로 일관 표현. publishing 단계에서 세션 로컬 매니페스트의 `work_units[].constituent_docs[].doc_instance_key`를 수집해 `setdefault(...).append(wu_key)`로 갱신하고 atomic rename(`.tmp → merge_index.json`)으로 커밋한다. **콘텐츠 `wu-*.md` 뒤에 마지막으로 커밋**하여 부분 publishing 상태가 스킵 판정에 노출되지 않게 한다. Phase B-0 스킵 판정 근거. |

### 중간 산출물 (세션 로컬 전용)

저장 경로: `skill_md2wu/queue/sessions/<session_id>/<caller_dirs>/` — `<terminal_phase>` 진입 후 §7 정리 단계에서 삭제. **전역으로 승격되지 않는다.**

| # | 산출물 | 파일명 패턴 (세션 로컬) | 설명 |
|:---:|:---|:---|:---|
| T1 | 헤딩·청크 통합 JSON | `parts/doc_parts.json` | 세션 내 전체 item의 `{headings, chunk_plan}`을 단일 JSON으로 통합 저장. Phase A가 headings를 채우고, Phase C가 claim한 item의 chunk_plan을 같은 파일에 덮어쓴다. |
| T2 | PRE 매니페스트 (통합 메타) | `out/corpus-{authority}_{doc_type}_{series}__pre__manifest.json` | corpus 공통 메타 + `work_units[]` (`wu_type`, `constituent_docs` 전체 객체, `chunk_keys`, `status`, `content_file`). F2(`merge_index.json`) 생성을 위한 소스이자 세션 감사용. **전역 경로에 올리지 않는다.** |
| T3 | Source Family 보고 | `out/corpus-{authority}_{doc_type}_{series}__md2wu__source_family_report.md` | 탐지 결과 및 승인 이력 |
| T4 | 분류 결과 | `out/corpus-{authority}_{doc_type}_{series}__md2wu__classification_result.json` | Authority·DocType·Heading Level |
| T5 | 이슈 게이트 보고 | `out/corpus-{authority}_{doc_type}_{series}__md2wu__issue_gate_report.json` | `threshold_issues` + `judgments`. 세션 디버그용. |
| T6 | 스테이지 로그 | `out/corpus-{authority}_{doc_type}_{series}__md2wu__stage_log.md` | 스테이지별 결정·이슈 누적 기록. 세션 감사용. |

> WU 개별 메타는 별도 파일(`wu-*__pre__meta.json`)을 만들지 않고 T2 매니페스트의 `work_units[]`에 직접 기록한다 (§"PRE 매니페스트 스키마" 참조).
>
> `<terminal_phase> = publishing` 시 전역 경로(`skill_md2wu/`)로 올리는 산출물은 **`wu-*__pre__content.md`(원자 `mv`)와 `merge_index.json`(atomic rename, 최후 커밋) 둘뿐이다.** 나머지 T2–T6은 세션 로컬에만 남고 §7 정리 시 삭제된다.

### 세션 산출물

저장 경로: `skill_md2wu/queue/sessions/<session_id>/`

| # | 산출물 | 상대 경로 | 설명 |
|:---:|:---|:---|:---|
| S1 | 스캔 인덱스 | `scan/scan_index.json` | Phase A 결과 (전체 파일 + source_family/series 포함) |
| S2 | 배치 계획 | `plans/batch_plan.json` | Phase B 결과 (`batch_capacity` 단위 배치 분할) |
| S3 | 작업 파일 | `pending/<item_id>/task.json` | item 단위 작업 명세 |
| S4 | 분류 결과 (item별) | `out/<item_id>__*.json` | Stage 4 결과 (T4 corpus 단위 결과의 item 단위 조각) |
| S5 | 배치 상태 | `logs/batch_{NNN}__status.json` | 배치별 진행 로그 |

> `parts/doc_parts.json`은 T1과 동일 파일이므로 본 표에서 별도 항목으로 두지 않는다.

---

## `parts/doc_parts.json` 스키마

세션 내 모든 item의 헤딩 트리·청크 계획을 하나의 JSON으로 관리한다.

```json
{
  "schema_version": 1,
  "session_id": "<session_uuid>",
  "items": {
    "<item_id>": {
      "headings": [ /* 헤딩 레코드 배열, 스키마는 아래 표 */ ],
      "chunk_plan": [ /* 청크 레코드 배열, null이면 Phase C 미수행 */ ]
    }
  }
}
```

### 헤딩 레코드 (`items[id].headings[]`)

| 필드 | 타입 | 설명 |
|:---|:---|:---|
| `heading_id` | string | `{document_key}_HD_{NNN}` (3자리 zero-pad) |
| `level` | int | 마크다운 헤딩 레벨 (1~6) |
| `start_line` | int | 헤딩 시작 줄 번호 |
| `end_line` | int | 헤딩 종료 줄 번호 (다음 동일/상위 레벨 헤딩 직전) |
| `title` | string | 헤딩 텍스트 (`#` 제외) |
| `parent_id` | string | 부모 헤딩 ID (루트면 빈 문자열) |
| `est_tokens_inclusive` | int | 하위 포함 토큰 수 |
| `est_tokens_exclusive` | int | 자체 콘텐츠만 토큰 수 |

### 청크 레코드 (`items[id].chunk_plan[]`)

각 청크 항목:

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

## PRE 매니페스트 스키마 (통합 메타)

`corpus-{authority}_{doc_type}_{series}__pre__manifest.json` — WU 개별 `wu-*__pre__meta.json` 파일을 만들지 않고, 그 모든 내용을 이 매니페스트 안에 흡수한다.

### Top-level (corpus 공통 메타)

| 필드 | 타입 | 설명 |
|:---|:---|:---|
| `corpus_scope` | string | `{authority}_{doc_type}_{series}` (예: `iacs_ur_z`) |
| `source_family` | string | 예: `iacs_ur` |
| `authority` | string | 발행 기관 (예: `IACS`) |
| `doc_type` | string | 문서 카테고리 (예: `UR`) |
| `language` | string | 언어 코드 (예: `en`) |
| `grammar_version` | string | 헤딩 문법 버전 |
| `measure_method` | string | `tiktoken` 또는 `char_approx` |
| `series` | string | 예: `ur_z` |
| `session_id` | string | 생성 세션 ID |
| `batch_id` | string | 생성 배치 ID |
| `generated_at` | string | ISO 8601 타임스탬프 |
| `wu_count` | int | `work_units` 길이 |
| `est_tokens_total` | int | 모든 WU 토큰 합 |
| `work_units[]` | array | 아래 WU 항목 스키마 |

### WU 항목 스키마 (`work_units[]`)

| 필드 | 타입 | 설명 |
|:---|:---|:---|
| `wu_key` | string | WU_Key |
| `wu_type` | string | `standalone` / `split` / `merged` |
| `constituent_docs[]` | array | 구성 문서 전체 객체 (`doc_instance_key`, `document_key`, `start_line`, `end_line`, `est_tokens`, `heading_range`) |
| `est_tokens_total` | int | WU 전체 토큰 수 |
| `chunk_keys[]` | array | 포함된 ChunkKey 목록 |
| `status` | string | `planned` → `processed` / `proceeded` / `revised` / `aborted` |
| `content_file` | string | 실제 콘텐츠 파일 경로 (`wu-{wu_key}__pre__content.md`) |

> corpus 공통 필드(`authority`, `doc_type`, `language`, `grammar_version`, `measure_method`, `created_at` 등)는 top-level에 한 번만 기록하고 `work_units[]`에서는 반복하지 않는다 (CLAUDE.md "중복된 내용은 지양" + SSOT).

---

## 실행 주체

본 스킬은 **결정적·기계적 연산을 Python 스크립트가 수행**하고, **에이전트(LLM)는 스크립트 호출·결과 해석·예외 판단**을 담당한다. 에이전트가 파싱·토큰 카운트·패킹 계산을 직접 수행하지 않는다.

### 사용 도구 (요약)

| 도구 | 용도 |
|:---|:---|
| `Bash` | `python heading_tokens.py`(S1–2), `python chunk_wu.py`(S5–6), `python manifest.py`(S7), `python coord_series.py`(공통). 큐 디렉토리 전이는 `mv`/`mkdir -p`/`rmdir`. 락은 Python `open(path, "x")` + `os.rename()` (queue-lock §3 규약). |
| `Read` | `parts/doc_parts.json`·`scan_index.json`·`batch_plan.json`·`merge_index.json`·기존 `shared/document_classification.md` 로드. |
| `Write` / `Edit` | 매니페스트(T2), 이슈 게이트 보고(T5), 스테이지 로그(T6), `wu-{wu_key}__pre__content.md`(F1) 생성·갱신. `merge_index.json`(F2)은 atomic rename으로 최후 커밋. |
| `Grep` | 헤딩 패턴·소스패밀리 단서 검색, 코드 블록 내 `#` 제외 보조. |
| `Skill` | 큐·락 규약은 [`queue-lock`](../queue-lock/SKILL.md) SSOT 참조(스킬 호출이 아니라 본문 §9 채택 선언). |
| `Agent` | 파일 수·총 토큰이 컨텍스트 압박을 줄 때만 서브에이전트로 분산(아래 "멀티 에이전트" 항목). 소량은 메인이 스크립트를 직접 호출. |

### 스크립트 카탈로그

| 스크립트 | 담당 단계 | 연산 내용 |
|:---|:---|:---|
| `heading_tokens.py` | S1–S2 | 헤딩 파싱, `tiktoken cl100k_base` 토큰 측정, 가산성 검증. 세션 로컬 `parts/doc_parts.json`에 `items[item_id].headings`로 병합 |
| `chunk_wu.py` | S5–S6 | 청크 분할, WU 패킹(Standalone/Split/Merged), 병합 제약 계산 |
| `manifest.py` | S7 | 이슈 집계, PRE 매니페스트 JSON 생성 |
| `coord_series.py` | 공통 | series_order 추출·시리즈 조율 |

### 단계별 할당

| 단계 | 실제 연산 | 에이전트 역할 |
|:---|:---|:---|
| **S1–2** | `heading_tokens.py` | 스크립트 호출, `doc_parts.json` 이상치 감지, 요약 반환 |
| **S3** | — (LLM 판단) | Source Family 후보 제시·사용자 승인 수집, 레퍼런스 갱신 |
| **S4** | — (경량 규칙) | Authority·DocType·Heading Level 추출 및 갱신 |
| **S5–6** | `chunk_wu.py` | 스크립트 호출, 오버사이즈/병합 예외 판단 |
| **S7** | `manifest.py` | 이슈 트리거 시 사용자 대화(`proceed`/`revise`/`abort`), publishing |

**멀티 에이전트**: 파일 수·총 토큰이 컨텍스트 압박을 줄 때만 서브에이전트로 분산한다. 소량일 때는 Coordinator가 스크립트를 직접 호출한다.

---

## 토큰 임계값 (기본값)

### 문서·청크·WU 레벨

| 파라미터 | 값 | 용도 |
|:---|:---|:---|
| `chunk_max` (Upper Bound) | 32K | 청크 분할 상한 |
| `chunk_exception` | 48K (1.5×) | 이 이하이면 분할하지 않고 예외 허용 |
| `wu_range` | 16K–32K | Standalone WU 목표 범위 |
| `wu_lower` | 16K | Merge 후보 기준 |

### 배치·세션 레벨 (Phase B)

| 파라미터 | 기본값 | 용도 |
|:---|:---|:---|
| `batch_capacity` | **600K** | 단일 배치의 합산 `cost_tokens` 상한 ([queue-lock §6.1](../queue-lock/SKILL.md)). 사용자/메모리 오버라이드 가능 (예: 200K). |
| `session_capacity` | `= batch_capacity` | 한 세션이 점유하는 최대 cost. 기본적으로 배치 용량과 동일 → **한 세션 = 1 배치**. |
| `stale_threshold` | 4h | 락 스테일 판정 mtime 임계. |

> 임계값은 사용자가 `shared/thresholds.yaml`을 제공하면 그 파일을 참조하고, 없으면 본 SKILL.md 본문의 기본값(표의 `chunk_max`·`wu_range`·`batch_capacity` 등)을 그대로 사용한다. 사용자가 `revise` 시 조정 가능. 사용자가 세션 예산을 직접 지정(예: 200K)하면 `batch_capacity`·`session_capacity` 모두 그 값으로 덮어쓴다.

---

## 사용자 승인 프로토콜 (Stage 3)

사용자에게 파일별로 **후보 Source Family + 판단 근거(헤딩 패턴, 레벨별 토큰 분포, 기존 분류와의 매칭 유사도) + 조치 선택지(승인 / 수정 / 거부)**를 함께 제시한다.

---

## 완료 조건

| # | 조건 |
|:---:|:---|
| 1 | 모든 대상 문서의 헤딩이 `parts/doc_parts.json`의 `items[<item_id>].headings`에 기록됨 |
| 2 | 가산성 검증 통과 (Error 0건) |
| 3 | Source Family 사용자 승인 완료, 레퍼런스 갱신 |
| 4 | Authority·DocType·Heading Level 추출 및 레퍼런스 갱신 |
| 5 | 청크 계획 + WU 패킹 계획 생성 |
| 6 | 이슈 게이트 처리 완료 (트리거 미발동 또는 사용자 응답 처리) |
| 7 | 세션 로컬 T2 매니페스트·T5 이슈게이트·T6 스테이지 로그 생성 (감사용, 전역 승격 금지) |
| 8 | 전역 `merge_index.json` atomic 갱신 (F2) — `wu-*__pre__content.md` 모두 커밋된 이후 **최후**에 커밋 |

---

## 스테이지 로그 (`corpus-{scope}__md2wu__stage_log.md`)

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

위 "필수 포함 항목" 표의 스테이지별 항목을 마크다운 섹션(`## Stage N: …`)으로 누적 기록한다. 상단에 대상 경로·실행일·총 토큰·최종 WU 수 요약 표를 붙인다.

---

## 제약 사항

- `.md` 파일만 처리. PDF/HTML은 사전 변환 필요 (pdf2md 등)
- 코드 블록 내부의 `#`은 헤딩이 아님
- 헤딩 없는 파일: 단일 Chunk로 처리 (Stage 5 폴백)
- `document_classification.md`가 제공된 경우에만 갱신하며 추가만 허용(기존 항목 삭제 금지). 파일이 없으면 갱신 자체를 생략하고 세션 내 메모리로만 기록.
- Split WU 조각은 다른 문서와 병합 불가
