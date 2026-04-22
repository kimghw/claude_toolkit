---
name: pdf2md
description: PDF를 구조화된 마크다운으로 변환. 원문 텍스트 무손실 보존, 이미지 추출·링크 삽입, 50p 단위 서브에이전트(opus) 분할 변환 후 병합, markdownlint·오탈자(en/ko) 검증. TRIGGER when 사용자가 PDF→MD 변환, 문서 마크다운화, PDF 구조화 요청. DO NOT TRIGGER when HTML/DOCX/JSON 변환, OCR 이미지 인식, 요약/번역 작업.
---

# pdf2md — PDF를 구조화 마크다운으로 변환

본 스킬은 PDF 파일을 원문 손실 없이 구조화된 마크다운으로 변환하는 절차를 정의한다. 50페이지 단위로 서브에이전트(opus 모델)를 병렬 할당하고, 각 에이전트는 담당 페이지 추출물을 Read 도구로 직접 읽어 변환하며, 이미지는 별도 파일로 추출하여 링크로 참조한다. **라운드당 최대 40개 서브에이전트**를 기동하며, **1개 파일의 모든 파트는 동일 라운드에서 처리**된다(파일 중간 분절 금지). **한 오케스트레이터 실행에서 총 파트(= 총 서브에이전트) 수는 기본 100개 이하(사용자 승인 시 초과 허용), 파일당 파트 수는 40개 이하(우회 불가)**이다.

본 스킬은 [howto-queue-lock](../howto-queue-lock/SKILL.md)의 락·큐 규약을 채택한다. 락 JSON 스키마·상태 전이·스테일·크래시 복구는 [howto-queue-lock §3](../howto-queue-lock/SKILL.md)을 그대로 따르며, 본 문서에는 pdf2md 고유 값(`<item_id> = <input>`, `state = pending|working|merging|failed`, `<caller_dirs> = pdf_parts/`·`assets/`·`out/`)과 변환 파이프라인만 선언한다.

## 스킬 구조

본 스킬은 **오케스트레이터**와 **서브에이전트** 두 주체의 책임을 명확히 분리한다.

- **3절 오케스트레이터 작업 범위**: 스킬 실행자(사용자와 대화하는 주체)가 수행하는 작업. 루트 준비, 글로벌 락 점유, 분해, 라운드 플래닝·실행, 병합, 검증, 정리.
- **4절 서브에이전트 프롬프트 템플릿**: Agent 호출 시 prompt에 포함할 동적 입력(경로, 조건 플래그)의 템플릿. 정적 지시문(변환 규칙, DO/DON'T, 체크리스트 등)은 Claude Code 서브에이전트 정의 파일 `.claude/agents/pdf2md-worker.md`의 시스템 프롬프트로 내장되어 있으며, 오케스트레이터가 `subagent_type: "pdf2md-worker"`로 Agent를 호출하면 자동 주입된다.

오케스트레이터의 핵심 원칙·절차·DO/DON'T·체크리스트는 3절에, 서브에이전트의 정적 지시문은 `.claude/agents/pdf2md-worker.md`에 각각 정의되어 있다.

## 사용 도구

본 스킬은 오케스트레이터(메인 세션)와 서브에이전트(`pdf2md-worker`)가 도구를 분담한다.

### 오케스트레이터

| 도구 | 용도 |
|:---|:---|
| `Agent` | `subagent_type: "pdf2md-worker"` + `run_in_background: true`로 라운드당 최대 40개 서브에이전트를 단일 메시지에서 병렬 기동. 정적 지시문은 `.claude/agents/pdf2md-worker.md`가 자동 주입. |
| `Bash` | `pdfinfo`(페이지 수 조회), `qpdf --pages` 또는 `pdfseparate+pdfunite`(파트 추출), `mv`/`mkdir -p`/`rm`(큐 디렉토리 전이·정리, **`rm -rf` 락 금지**), `markdownlint`(병합 후 검증), `python3 -m language_tool_python` 또는 `scripts/filter_typo_report.py`(오탈자 검증·필터링), `sed -i`(이미지 링크 재작성). |
| `Read` / `Write` / `Edit` | 락 JSON·`task.json`·`scan_index.json`·`partNN.md` 입출력, `markdownlint_rules.md` 갱신, 병합 결과 자가 수정. |
| `Grep` | 헤딩 순서·이미지 링크 일치 검증 시 패턴 매칭. |
| (외부 CLI) | `qpdf`, `pdfinfo`, `pdfseparate`/`pdfunite`, `pdfimages`(서브에이전트 책임), `markdownlint`, Python `language_tool_python`. |

### 서브에이전트(`pdf2md-worker`)

| 도구 | 용도 |
|:---|:---|
| `Read` | `part_source` PDF 직독(텍스트 사전 추출 금지). |
| `Bash` | `pdfimages -all`로 담당 파트 이미지 추출. |
| `Write` / `Edit` | `partNN.md` 생성, 이미지 링크 삽입. |

> 서브에이전트의 도구·절차 상세는 [.claude/agents/pdf2md-worker.md](../../agents/pdf2md-worker.md) 시스템 프롬프트가 SSOT이며, 본 표는 외부에서 본 사용 도구 요약이다.

## 1. 용어

- **오케스트레이터(Orchestrator)**: 본 스킬을 실행하는 주체이자 사용자의 협력자. 사용자의 요청을 받아 큐 구성, 서브에이전트 호출·조율, 병합, 이미지 집계·링크 재작성, 검증, 정리, 보고를 담당한다.
- **서브에이전트(Sub-agent)**: 오케스트레이터가 Agent 도구로 호출하는 opus 변환 에이전트. 담당 페이지 구간 1개만 변환하며 사용자와 직접 대화하지 않는다. 결과·오류는 오케스트레이터에게만 전달한다.
- **part_source**: 서브에이전트가 Read 도구로 직독하는, 담당 페이지만 포함된 PDF 추출물. 오케스트레이터가 분해 시 qpdf로 사전 생성한다.
- **조건 플래그**: 오케스트레이터가 분해 시 확정하여 프롬프트 슬롯에 주입하는 파트별 메타데이터(`part_index`, `is_first_part` 등). 서브에이전트의 조건부 분기 행동을 결정한다.
- **라운드(Round)**: 한 번의 병렬 배치 실행 사이클. **라운드당 서브에이전트 수는 최대 40개(절대 상한)**. 1개 파일의 파트는 반드시 동일 라운드에 포함되며(중간 분절 금지), 여러 파일을 라운드 용량(40) 한도 내에서 묶어 실행한다. **전체 실행(모든 라운드 합산)에서 서브에이전트 수는 최대 100개(절대 상한)**이다. 총 100 / 라운드당 40이므로 최대 라운드 수는 `ceil(100/40) = 3`이다.
- **세션 ID(session_id)**: Claude Code가 세션마다 자동 부여하는 UUID(`~/.claude/projects/<project>/` 내 `.jsonl` 파일명). 글로벌 락의 owner 기록과 로그 식별자로 사용한다. 별도 발급 절차 없이 현재 세션 ID를 그대로 쓴다.
- **글로벌 락(Global Lock)**: `<workroot>/queue/locks/<input>.lock` **단일 JSON 파일(정규 파일, 디렉토리 아님)**. 여러 오케스트레이터가 같은 `<workroot>`를 공유할 때 **파일 단위 배타 점유**를 보장하여 동일 작업 중복 실행을 방지한다. 파일 내용은 [howto-queue-lock §3](../howto-queue-lock/SKILL.md) 스키마를 따르는 단일 라인 JSON `{"owner":"<session_id>","state":"pending|working|merging|failed","claimed_at":"<ISO8601>","updated_at":"<ISO8601>"}`이다. `owner`·`claimed_at`은 불변, `state`·`updated_at`은 상태 전이 시 atomic replace로 갱신한다.

## 2. 입력 / 출력 규약

- **입력**: 단일 또는 다중 PDF 경로 (`<input>.pdf` …), 또는 **폴더 경로**. 폴더가 주어지면 해당 폴더 내 모든 `*.pdf` 파일을 대상으로 한다.
- **파트 수 상한**:
  - **총 파트 수 (권장 100, 사용자 승인 시 초과 허용)**: 스킵 판정을 끝낸 순 변환 대상 파일들에 대해 파일당 `ceil(pages/50)`을 합산한 값이 **100을 초과하면 절차 2 이하로 진행하지 말고 사용자에게 승인 요청**한다. (과거의 "파일 수 100건 상한" 규약은 폐지되었다.)
  - **파일당 파트 수 (절대 40, 우회 불가)**: 1개 파일의 `ceil(pages/50)`이 40을 초과하면 단일 라운드(최대 40개)에 수용될 수 없으므로 사용자에게 `qpdf --pages` 등을 통한 물리 분할을 요청하고 해당 파일은 이번 실행에서 제외한다. 이 제약은 "1 파일 = 1 라운드" 원칙의 귀결이며 승인으로 우회할 수 없다.
- **변환 완료 스킵**: 폴더 입력 시 오케스트레이터는 변환 대상 목록을 확정하기 전에 **기존 산출물 존재 여부**를 검사한다. `<원본폴더>_md/<input>.md`가 이미 존재하고 크기 > 0이면 해당 PDF는 **변환 완료(skipped)**로 분류하여 큐에 적재하지 않는다. 스킵된 파일 목록은 사용자에게 보고하고 `agent_report.md`에도 기록한다.
- **최종 산출 경로**: 최종 `.md` 파일은 **원본 PDF가 위치한 폴더의 이름에 `_md` 접미사를 붙인 폴더**에 저장한다. 예: 원본이 `docs/manual/foo.pdf`이면 최종 산출물은 `docs/manual_md/foo.md`. 동일 폴더 내 다중 PDF는 같은 `<원본폴더>_md/`에 모두 저장.
- **작업 루트**: `<workroot>/` (기본값 `./pdf2md_work/`).
- **작업 디렉토리 레이아웃**:

  ```text
  <workroot>/
  └── queue/
      ├── locks/<input>.lock            ← 파일 단위 글로벌 락 (단일 JSON 정규 파일, O_CREAT|O_EXCL로 배타 점유, 세션 간 조율)
      │                                   내용: {"owner":"<session_id>","state":"pending|working|merging|failed","claimed_at":"<ISO8601>","updated_at":"<ISO8601>"}
      └── sessions/<session_id>/        ← 세션별 격리 (session_id = 현재 세션 UUID)
          ├── pdf_parts/                ← 오케스트레이터가 qpdf로 사전 생성한 파트별 PDF 추출물
          ├── pending/<input>/partNN.task.json  ← 적재 대기 파트
          ├── working/<input>/          ← 진행 중 파트 (partNN.task.json + partNN.md)
          ├── done/<input>/             ← 서브에이전트 완료·후처리 완료 (병합 입력)
          ├── failed/<input>/           ← 재시도 임계 초과로 분리된 파트
          ├── assets/<input>/           ← 서브에이전트가 pdfimages로 추출 (partNN-fig-XXX.ext)
          └── out/                      ← 병합·린트 스테이징

  <원본폴더>_md/<input>.md      ← 최종 병합 산출물 (검증 통과 후 배치)
  <원본폴더>_md/assets/<input>/ ← 최종 이미지 사본
  ```

  - **상대경로 불변**: `sessions/<session_id>/working/<input>/partNN.md`에서 `sessions/<session_id>/assets/<input>/`까지는 `../../assets/<input>/`(2단계 상위 = `sessions/<session_id>/`, 그 하위 `assets/<input>/`). 세션별 격리 구조에서도 `working/`과 `assets/`가 같은 세션 디렉토리 하위에 있으므로 상대경로 깊이(`../../`)는 변하지 않는다. 서브에이전트 이미지 링크 규약과 병합 후 sed 재작성 로직은 이 상대경로를 유지한다.

- **글로벌 락 프로토콜**:
  - **점유 시도**: `<workroot>/queue/locks/<input>.lock` 파일을 `O_CREAT|O_EXCL|O_WRONLY`로 생성 시도(Python 기준 `open(path, "x")`). POSIX `open(2) + O_EXCL`은 원자적이며 파일이 이미 존재하면 `EEXIST`로 실패한다. 실패 = 다른 오케스트레이터가 점유 중 → 해당 파일을 스킵하고 다음 파일로 진행한다.
  - **점유 성공 시 즉시 기록**: 생성된 파일 핸들에 `{"owner":"<session_id>","state":"pending","claimed_at":"<ISO8601>","updated_at":"<ISO8601>"}` 단일 라인 JSON을 **한 번의 `write()`로 기록한 뒤 닫는다**. 이렇게 하면 빈 파일 관찰 창을 최소화할 수 있으나 [howto-queue-lock §3.1](../howto-queue-lock/SKILL.md)이 명시한 대로 완전히 제거하지는 못한다 — 락 본문을 읽는 측은 빈 파일/JSON 파싱 실패를 "점유 진행 중"으로 해석하는 howto-queue-lock 규약을 따른다.
  - **상태 전이 (atomic replace 규약, 필수)**: `state`를 `pending → working → merging`(또는 `failed`)로 갱신할 때는 **절대로 기존 락 파일을 `open("w")`로 덮어쓰지 않는다**. 같은 디렉토리에 임시 파일 `<input>.lock.tmp.<pid>`를 생성하여 새 JSON(`state`와 `updated_at`을 함께 현재 시각으로 갱신; `owner`·`claimed_at`은 불변)을 기록한 뒤 `os.rename(<tmp>, <lockfile>)`로 원자 교체한다(POSIX `rename(2)` 원자성). 덮어쓰기 방식은 다른 오케스트레이터가 반쯤 쓰인 JSON을 읽을 수 있으므로 금지한다.
  - **해제**: 해당 파일의 병합·검증·최종 배치가 성공하면 `os.unlink(<workroot>/queue/locks/<input>.lock)` (쉘에서는 `rm <workroot>/queue/locks/<input>.lock`, **`rm -rf` 금지**). 실패(재시도 임계 초과 포함)로 종료하면 락 파일을 삭제하지 않고 atomic replace 규약으로 `state=failed`만 갱신한 채 남겨 사용자에게 수동 복구를 요청한다.
  - **스테일 락**: 락 파일의 mtime이 `stale_threshold`(기본 4시간) 이상이고 `state`가 진행 중이면 사용자에게 보고한다. 상태 전이 시마다 atomic replace으로 mtime이 갱신되므로 살아있는 오케스트레이터의 락은 자연스럽게 "살아있음" 신호를 남긴다. **자동 탈취는 하지 않는다**(오진행 중인 다른 오케스트레이터의 작업을 덮어쓸 위험).

- **큐 작업 파일**: `partNN.task.json` — 입력 PDF 경로, part_source 경로, 페이지 범위, 조건 플래그, 출력 조각 경로, 이미지 디렉토리, 상태. `sessions/<session_id>/pending/<input>/` → `sessions/<session_id>/working/<input>/` → `sessions/<session_id>/done/<input>/` 순서로 `mv`로 원자 이동(POSIX `rename(2)`).
- **중간 산출물**: `<workroot>/queue/sessions/<session_id>/done/<input>/partNN.md` — 최종 정리(절차 8)에서 해당 파일의 큐·자산 정리와 함께 삭제된다.
- **`agent_report.md` (감사 로그)**: 경로는 `<workroot>/queue/sessions/<session_id>/agent_report.md`. 오케스트레이터(메인 세션)가 생성·소유하며 서브에이전트는 기록하지 않는다. 형식은 append-only 마크다운으로, 스킵 목록·오탈자 자동 수정·미수정 항목·markdownlint 규칙 갱신 내역 등 사용자 보고 대상 이벤트를 기록한다. 엔트리는 `## [<ISO8601>] <작업명>` 헤더로 시작하고 본문에 세부 내역을 넣는다. 파일이 없으면 첫 append 시 생성한다. publishing 완료 및 §8 정리 단계에서 세션 디렉토리와 함께 삭제된다(감사 기록을 보관해야 할 경우 사용자가 정리 전에 외부로 복사).

---

## 3. 오케스트레이터 작업 범위

### 3.1 핵심 원칙 (오케스트레이터)

- **무손실 보존 감독**: 서브에이전트가 원문 텍스트를 삭제·의역·요약하지 않았는지 병합 후 스폿 체크한다.
- **분할 변환**: 총 페이지 > 50이면 50p 단위로 분할, 구간당 서브에이전트 1개(opus)를 할당한다. 여러 파일을 한 번에 처리할 때도 각 파일을 동일 규칙으로 분해하고 단일 큐로 묶는다. **제약**: 파일당 파트 수 ≤ 40(단일 라운드 수용), 총 파트 수 ≤ 100(전 실행 합산).
- **큐 기반 작업 관리**: 작업 단위(= 한 구간)는 **`sessions/<session_id>/pending/<input>/` → `sessions/<session_id>/working/<input>/` → `sessions/<session_id>/done/<input>/`** 순서로 이동한다. `mv`로 원자 이동하여 점유 경합을 막는다(POSIX `rename(2)` 원자성). 서브에이전트가 완료되면 오케스트레이터가 후처리(메타데이터 파싱) 후 `sessions/<session_id>/working/<input>/` → `sessions/<session_id>/done/<input>/`으로 이동한다.
- **글로벌 락으로 배타 점유**: 오케스트레이터는 파일 단위로 `locks/<input>.lock` 단일 파일을 `O_CREAT|O_EXCL`로 원자 생성하여 점유한다. 점유 실패(다른 오케스트레이터가 이미 점유)면 해당 파일을 스킵하고 다음으로 진행한다. 점유한 파일만 `pending/`·`working/`·`done/`에 적재·이동한다.
- **비동기 병렬 실행**: 서브에이전트는 `run_in_background: true`로 기동하여 오케스트레이터가 블로킹되지 않게 한다. **라운드당 동시 기동 수는 최대 40개(절대 상한)**, **전체 실행에서 총 기동 수는 최대 100개(절대 상한)**.
- **1 파일 = 1 라운드**: 1개 파일의 모든 파트는 동일 라운드에 포함된다. 여러 파일을 한 라운드에 합칠 수 있으나(합계 ≤ 40), 하나의 파일을 두 라운드에 나누어 실행하지 않는다.
- **큰 파일 우선 처리**: 라운드 플래닝·큐 적재·점유 순서는 모두 **파트 수 내림차순(= 큰 파일 우선)**으로 수행한다. 큰 파일을 먼저 배치해야 라운드 패킹 효율(First-Fit Decreasing)이 최적이고, 대용량 파일이 마지막 라운드에 몰려 실패 시 재시도 비용이 커지는 상황을 방지한다.
- **즉시 처리**: 서브에이전트 완료 알림이 도착하면 오케스트레이터는 즉시 후처리(메타데이터 파싱)를 수행하고 `sessions/<session_id>/working/<input>/` → `sessions/<session_id>/done/<input>/`으로 이동한다. 한 소스 파일의 모든 파트가 `sessions/<session_id>/done/<input>/`에 모이면 병합(절차 6)·검증(절차 7)을 즉시 수행한다.
- **사전 가공의 허용 범위**: PDF 전처리는 **페이지 분할(`qpdf --pages` 또는 `pdfseparate`+`pdfunite`), 메타데이터 조회(`pdfinfo`)에 한정**한다. `pdftotext`·`pymupdf`·`pdfminer` 등 본문 텍스트 추출 도구를 본문 변환 목적으로 사용하지 않는다.
- **병합 후 단일 산출물**: 파일 1개당 최종 출력은 `.md` 1개. 페이지 단위 구분 마크·구간 간 마크 모두 삽입하지 않는다.
- **검증 필수**: 병합 후 markdownlint + 헤딩 순서·계층·표기 일치 검증 + 이미지 링크 해소 검증 + 오탈자 검사(en/ko)를 수행하고 위반 사항을 수정한다.
- **첨자 디렉티브 주입 책임**: 완료 보고에서 첨자 사용 플래그를 수집하고, 병합 후 파일 최상단에 MD033 disable 디렉티브를 1회 주입한다.
- **경계 이어붙임 책임**: 파트 경계에서 잘린 문단·목록·표를 병합 시 판정하여 이어붙인다.

#### 서브에이전트 위임 사항

오케스트레이터가 프롬프트 설계·경로 전달을 통해 **보장해야 할** 서브에이전트 측 행동 원칙. 구체적 절차는 4절 서브에이전트 지시문에 정의되어 있으며, 아래는 오케스트레이터가 위임 구조를 올바르게 유지하기 위한 체크포인트다.

- **단일 책임 위임**: 프롬프트에 `part_source` 경로만 전달하여 타 구간 참조·수정이 발생하지 않게 한다.
- **직독 원칙 보장**: 본문을 사전 텍스트화하여 문자열로 넘기지 않는다. `part_source` PDF 경로만 전달하여 에이전트가 Read 도구로 직접 읽게 한다.
- **정적 지시문 자동 로드**: 변환 규칙·절차·DO/DON'T 등 정적 지시문을 prompt에 복사하지 않는다. Agent 호출 시 `subagent_type: "pdf2md-worker"`를 지정하여 `.claude/agents/pdf2md-worker.md`의 시스템 프롬프트가 압축·잘림 없이 자동 주입되게 한다.
- **이미지 추출 위임**: 이미지 추출(`pdfimages`)은 서브에이전트에 위임한다. 오케스트레이터는 병합 시 이미지 집계와 경로 재작성만 담당한다.

### 3.2 절차

1. **입력 스캔 및 스킵 판정 · 파트 수 상한 검증**
   - 입력이 폴더이면 `*.pdf` 파일 목록을 수집한다.
   - 각 PDF에 대해 `<원본폴더>_md/<input>.md` 존재 여부를 확인한다(`test -f`, 크기 > 0).
   - 이미 산출물이 존재하는 PDF는 **skipped** 목록에 추가하고 변환 대상에서 제외한다.
   - 스킵 결과를 사용자에게 즉시 보고한다(예: `"3/5 파일 변환 완료 — 스킵: foo.pdf, bar.pdf, baz.pdf / 변환 대상: qux.pdf, quux.pdf"`).
   - 변환 대상이 0개이면 "모든 PDF가 이미 변환됨"을 보고하고 종료한다.
   - **파트 수 사전 산출**: 각 대상 파일에 대해 `pdfinfo <input>.pdf`로 총 페이지 수를 조회하고 `ceil(pages/50)`로 파트 수를 계산한다.
   - **파일당 파트 수 상한 (절대 40, 우회 불가)**: 파트 수 > 40인 파일은 즉시 변환 대상에서 제외하고 사용자에게 `qpdf --pages`로 물리 분할을 요청한다. 이 제약은 "1 파일 = 1 라운드" 원칙의 귀결이므로 승인으로 우회할 수 없다.
   - **총 파트 수 상한 (권장 100)**: 남은 대상 파일들의 파트 합계가 100을 초과하면 **절차 2 이하로 진행하지 말고 사용자에게 승인 요청**하거나 우선순위 하위 파일을 제외한다.

2. **작업 루트 준비 · 세션 ID 확인**
   - **session_id 확인**: 현재 Claude Code 세션의 UUID를 `session_id`로 사용한다. 별도 발급 절차 없이 `~/.claude/projects/<project>/` 내 현재 세션 `.jsonl` 파일명에서 확인할 수 있다.
   - **큐 트리 확보**: `<workroot>/queue/locks/`와 `<workroot>/queue/sessions/<session_id>/{pdf_parts,pending,working,done,failed,assets,out}/`을 `mkdir -p`로 준비한다(이미 존재하면 건드리지 않는다).

3. **사전 조사** (파일별)
   - 절차 1에서 조회한 총 페이지 수를 재사용(캐싱 가능).
   - `mkdir -p <workroot>/queue/sessions/<session_id>/assets/<input>/` — 서브에이전트가 이미지를 추출할 디렉토리를 사전 생성한다.

4. **글로벌 락 점유 · 분해 · 플래그 확정 · 추출물 생성 · 큐 적재**
   - **처리 순서**: 파일 목록을 **파트 수 내림차순(큰 파일 우선)**으로 정렬한 뒤 순회한다. 큰 파일이 먼저 점유·분해되어야 총 파트 100 상한 소진 시 남는 자리가 작은 파일로 채워지고, 라운드 플래닝 단계(5.0)의 First-Fit Decreasing 패킹과도 일관된다.
   - 각 파일에 대해 다음을 수행한다.
   - **글로벌 락 점유**: `<workroot>/queue/locks/<input>.lock` 파일을 `O_CREAT|O_EXCL|O_WRONLY`로 생성 시도(Python `open(path, "x")`).
     - **실패** (`EEXIST`, 다른 오케스트레이터가 점유 중): 해당 파일을 스킵하고 사용자에게 보고. 다음 파일로 진행.
     - **성공**: 즉시 `{"owner":"<session_id>","state":"pending","claimed_at":"<ISO8601>","updated_at":"<ISO8601>"}` 단일 라인 JSON을 **한 번의 `write()`로 기록**하고 파일 핸들을 닫는다.
   - 파일당 `ceil(total/50)`개 구간을 계산(이미 절차 1에서 검증된 값, 40 이하).
   - 점유 성공 파일들의 파트 수를 누적하여 **총 파트 수 ≤ 100**(= `session_capacity`)을 유지한다. 초과 예정이면 해당 파일과 그 이후 파일은 **락 claim을 시도하지 않고, pending 적재도 하지 않은 채** 다음 세션/계정이 가져갈 수 있도록 원본 상태로 보존한다([howto-queue-lock §6.6](../howto-queue-lock/SKILL.md)). 사용자에게는 "N개 파일을 다른 세션용으로 보존함"을 보고한다.
   - 각 구간에 대해 **조건 플래그**를 확정한다(3.3 참조).
   - 각 구간마다 **담당 페이지 추출물**을 사전 생성하여 `<workroot>/queue/sessions/<session_id>/pdf_parts/<input>__partNN.pdf`에 저장.
     - **권장 (qpdf)**: `qpdf <input>.pdf --pages <input>.pdf <start>-<end> -- <workroot>/queue/sessions/<session_id>/pdf_parts/<input>__partNN.pdf`
     - **대안 (pdfseparate + pdfunite)**: `pdfseparate -f <start> -l <end> <input>.pdf /tmp/_p_%d.pdf && pdfunite /tmp/_p_*.pdf <workroot>/queue/sessions/<session_id>/pdf_parts/<input>__partNN.pdf && rm /tmp/_p_*.pdf`
     - **절대 금지**: `pdfseparate` 단독 사용(페이지별 파일이 생성되어 단일 추출물이 되지 않음).
     - **참고**: 총 페이지 ≤ 50이고 파트가 1개뿐이면 원본 PDF를 그대로 `cp`하여 `partNN.pdf`로 두어도 무방. `sessions/<session_id>/pdf_parts/`에 동일 파일명이 이미 존재하면 재생성하지 않는다.
   - 각 구간의 **작업 파일** `partNN.task.json`을 생성(입력 PDF 경로, part_source 경로, 페이지 범위, 조건 플래그, 출력 조각 경로, 이미지 출력 디렉토리, 상태).
   - 작업 파일을 `<workroot>/queue/sessions/<session_id>/pending/<input>/partNN.task.json`으로 적재한다. 다중 입력 파일은 각자 `sessions/<session_id>/pending/<input>/` 서브디렉토리로 분리 적재한다(평탄화하지 않는다).

5. **라운드 실행** (라운드 단위 순차 배치)

   오케스트레이터는 점유한 파일들의 모든 파트를 **라운드로 묶어 순차 실행**한다. 한 라운드는 최대 40개의 서브에이전트를 병렬 기동하며, 1개 파일의 파트는 항상 동일 라운드에 포함된다(분절 금지).

   **5.0 라운드 플래닝**
   - 점유한 파일 목록을 파트 수 **내림차순**으로 정렬한다(큰 파일 우선 배치 → First-Fit Decreasing).
   - 각 파일을 현재 라운드에 시도 추가한다.
     - (현재 라운드 파트 합) + (파일 파트 수) ≤ 40 → 현재 라운드에 추가.
     - 초과 → 현재 라운드를 확정하고 새 라운드를 시작해 해당 파일을 넣는다.
   - 결과: 라운드 리스트(각 라운드 = 파일 집합, 파트 합 ≤ 40). 총 파트 수 ≤ 100이 보장되므로 **라운드 수는 최대 3**(`ceil(100/40)`)이다.

   **5a. 라운드 시작 — 서브에이전트 기동**
   - 현재 라운드에 포함된 파일들의 작업 파일을 `mv <workroot>/queue/sessions/<session_id>/pending/<input> <workroot>/queue/sessions/<session_id>/working/<input>`로 일괄 이동한다.
   - 락 상태를 `working`으로 갱신한다: **atomic replace 규약**으로 `locks/<input>.lock.tmp.<pid>`에 새 JSON(`state="working"`, `updated_at=<현재 ISO8601>`; `owner`·`claimed_at`은 보존)을 기록한 뒤 `os.rename()`으로 `locks/<input>.lock`을 원자 교체한다. 기존 락 파일을 직접 덮어쓰는 것은 금지.
   - 라운드의 **모든 파트**(최대 40개)를 **단일 메시지**에서 다중 Agent 호출로 병렬 기동한다. 각 호출은 `subagent_type: "pdf2md-worker"` + `run_in_background: true`.
   - 에이전트 프롬프트는 **4.1(역할/입력)과 4.2(조건 플래그)만 포함**하고 플레이스홀더를 실제 값으로 치환한다. 정적 지시문은 `pdf2md-worker` 서브에이전트 정의에 내장되어 자동 주입된다(3.4 참조).

   **5b. 완료 처리 (완료 알림 도착 시마다)**
   - 서브에이전트 완료 알림이 도착하면 오케스트레이터는 즉시:
     1. 완료 보고를 파싱하여 파일별 메타데이터에 누적(특히 `첨자_발견` 플래그, `추출_이미지_수` 합계).
     2. 해당 `partNN.task.json`과 생성된 `partNN.md`를 `sessions/<session_id>/working/<input>/` → `sessions/<session_id>/done/<input>/`으로 이동.
     3. 해당 입력 파일의 모든 파트가 `sessions/<session_id>/done/<input>/`에 모였으면 락 상태를 **atomic replace 규약**으로 `merging`으로 갱신하고 절차 6(병합)·절차 7(검증)을 **즉시** 수행한다. 검증 통과 시 **절차 8에 따라 큐·자산 정리를 모두 마친 후** 락 파일을 `os.unlink`로 해제한다.
     4. 실패한 작업은 `sessions/<session_id>/working/<input>/` 내부에서 재시도 카운트를 증가시킨 뒤 **동일 라운드 내에서 재기동**한다. 임계(기본 2회) 초과 시 `sessions/<session_id>/failed/<input>/`로 분리하고 보고한다. 재시도는 100 총 상한에 포함되지 않는다(이미 집계된 파트의 재실행).

   **5c. 라운드 종료 판정 · 다음 라운드**
   - 현재 라운드의 모든 파트가 `sessions/<session_id>/done/<input>/` 또는 `sessions/<session_id>/failed/<input>/`에 도달하면 라운드가 종료된다.
   - 남은 라운드가 있으면 5a로 이동하여 다음 라운드를 기동한다(백그라운드 완료 알림을 모두 수신한 뒤 시작).
   - 남은 라운드가 없으면 절차 8(최종 정리)로 진행한다.

   **5d. 교차 라운드 금지**
   - 1개 파일의 파트는 반드시 동일 라운드에 포함된다. 완료된 파트와 실패한 파트가 섞여 있어도 해당 파일의 재시도는 **같은 라운드 내에서** 처리한다(다음 라운드로 이월하지 않는다).
   - 재시도 임계를 초과한 파트가 있으면 해당 파일은 이번 실행에서 실패로 종료하고, **atomic replace 규약**으로 락 파일을 `state=failed`로 갱신한 채 남겨 사용자에게 보고한다(락 파일 삭제 금지).

6. **병합** (파일별)
   - 한 입력 파일의 모든 구간이 `sessions/<session_id>/done/<input>/`에 모인 시점에 해당 파일 병합을 수행한다.
   - `part01.md`부터 순서대로 단순 연결 → `<workroot>/queue/sessions/<session_id>/out/<input>.md` (스테이징 위치).
   - **경계 이어붙임**: 각 파트 경계에서 `partNN.md`의 마지막 줄과 `part(NN+1).md`의 첫 줄을 검사한다.
     - 문단 단편(문장 중간에서 끝남) → 한 칸 공백으로 이어붙임.
     - 목록 계속(불릿/번호 목록이 경계를 넘나듦) → 목록 구조를 하나로 복원.
     - 표 계속(헤더 없이 시작하는 표 행) → 앞 파트 표에 병합.
     - 내용 자체는 변경하지 않고 구조만 복원한다.
   - **첨자 디렉티브 주입**: 어느 파트라도 완료 보고에 `첨자 발견: true`가 있으면 병합 파일 최상단(H1 바로 위)에 `<!-- markdownlint-disable MD033 -->`를 1회 삽입한다.
   - **이미지 집계**: `<workroot>/queue/sessions/<session_id>/assets/<input>/`에 서브에이전트들이 추출한 이미지(`partNN-fig-XXX.ext`)를 `<원본폴더>_md/assets/<input>/`으로 복사한다. 대상 디렉토리가 없으면 `mkdir -p`로 생성. 파트별 접두사(`partNN-fig-`)로 파일명 충돌이 없으므로 단순 복사.
   - **이미지 링크 재작성**: 서브에이전트는 `sessions/<session_id>/working/<input>/partNN.md` 기준 `../../assets/<input>/...` 상대경로를 사용했으므로(2단계 상위 = `sessions/<session_id>/`, 그 하위 `assets/<input>/`), 병합 파일의 링크를 최종 위치 기준 `assets/<input>/...`로 일괄 재작성한다. 예: `sed -i 's|\.\./\.\./assets/<input>/|assets/<input>/|g' <파일경로>`.

7. **검증 및 최종 배치**
   - `markdownlint <workroot>/queue/sessions/<session_id>/out/<input>.md` 실행.
   - 대상 규칙: 제목 계층 순서(MD001), 넘버링 증가(MD029), 중복 제목(MD024), 링크 유효성(MD042), H1 1개(MD025), 첫 줄 H1(MD041), 표 형식 등.
   - **헤딩 순서·표기 검증(필수)**: 원문 PDF의 목차/장·절 번호를 기준으로 최종 `.md`의 헤딩이 다음을 만족하는지 확인한다.
     - **순서 일치**: 원문 등장 순서대로 배열, 누락·중복·역전 없음.
     - **계층 일치**: 원문의 장·절·하위절 깊이에 맞춰 `#`~`######` 레벨이 부여되었고, 한 단계 이상 건너뛰지 않음.
     - **표기 일치**: 번호 체계와 제목 텍스트가 원문과 동일(임의 축약·번역·번호 재부여 금지).
   - **위반 발생 시 자가 수정**: 오케스트레이터가 직접 해당 `.md`를 수정하여 해소한 뒤 재검증한다. 수정 범위는 구조·포맷(제목 계층, 넘버링, 공백, 링크 형식 등)에 한정하며 원문 텍스트·의미는 변경하지 않는다. 원문을 건드려야만 해결되는 위반이거나 자동 판단이 어려운 경우는 중단하고 사용자에게 보고한다.
   - **이미지 링크 해소 검증**: 최종 경로 배치 후 모든 이미지 링크(`![...](...)`)의 실제 파일 존재 여부를 `test -f`로 확인한다. 실패 시 절차 6의 이미지 집계/재작성을 재수행한다.
   - **오탈자 검사 (필수)**: `language_tool_python` 패키지로 영문(`en-US`)·국문(`ko-KR`) 오탈자를 검출한다. 언어 판정은 한글 문자 비율 기준(≥0.3 → ko, 혼재 시 둘 다 실행). **전처리**: LanguageTool에 텍스트를 넘기기 전에 수식 구간(`$$...$$` 블록, `$...$` 인라인)과 HTML 주석(`<!-- ... -->`)을 빈 문자열로 치환하여 수식 토큰 오탐을 방지한다. 자동 수정 범위는 **단일 후보 + 카테고리 `TYPOS`/`MISSPELLING`**에 한정하되, **`BRITISH_ENGLISH_DETECTOR` 룰은 자동 수정에서 제외**한다(원문이 영국식 영어인 경우 그대로 보존). 다중 후보·문맥 의존·문법 카테고리는 수정하지 않고 위치·원문·후보 목록을 사용자에게 보고한다. 리포트 생성 자체는 필수이며, 후처리(화이트리스트 기반 False Positive 필터링)는 **선택 단계**다: `scripts/filter_typo_report.py`와 `shared/typo_whitelist.yaml`이 **둘 다 존재할 때만** `python3 scripts/filter_typo_report.py`를 실행한다. 둘 중 하나라도 없으면 필터링을 건너뛰고 원본 리포트를 그대로 수용한다(스킬 실패로 간주하지 않는다). 자동 수정·미수정 항목 모두 `agent_report.md`에 append한다. 수정 결과는 markdownlint를 재실행하여 재검증한다.
   - **이미지 0개 케이스도 명시 보고**: 이미지가 0개인 입력 파일이라도 "링크 0/0 통과(이미지 없음)"로 사용자 보고에 명시한다. vacuously true임을 암묵 처리하지 않는다.
   - **사용자 보고**: 어떤 규칙이 어디서 위반되었고 어떻게 수정했는지(파일·줄·규칙ID·수정 요지)를 사용자에게 요약 보고하고, `agent_report.md`에도 append한다(타임스탬프 + 작업명 헤더).
   - **규칙 가이드 피드백 갱신(필수)**: markdownlint 실행 결과가 나오면 오케스트레이터는 `.claude/skills/pdf2md/markdownlint_rules.md`를 갱신한다. 갱신 절차:
     1. 먼저 Read로 기존 파일 전체를 읽어 등록된 규칙(`MD###`)과 분류(변환 시점 회피 / 병합 후 검증)를 파악한다.
     2. 이번 실행에서 관찰된 위반 규칙을 기존 항목과 대조한다.
        - **이미 등록된 규칙**: 중복 추가 금지. 필요 시 설명·예시만 보강한다(기존 문장 의미를 뒤집지 않는 범위에서).
        - **미등록 규칙**: 해당 섹션("변환 시점에 피할 수 있는 규칙" 또는 "병합 후 검증 대상 규칙")에 동일 형식(`- **MD###** (rule-name): 설명`)으로 append.
        - **기존 설명과 충돌·상충**: 기존 문구를 임의 수정하지 않는다.
     3. **차이가 큰 경우**(신규 규칙 3개 이상, 또는 기존 분류/설명을 뒤집어야 하는 변경)에는 파일 본문을 직접 수정하지 말고, 파일 **하단에 `## 사용자 협의 필요` 섹션**을 만들거나 이어 붙여 `- [YYYY-MM-DD] <입력파일>: <관찰 내용>, <제안>` 형식으로 append한다. 사용자 결정 전까지 상단 규칙 섹션은 건드리지 않는다.
     4. 갱신 시 SKILL.md 본문에 규칙을 재이식하지 않는다(SSOT 위반).
   - **린트 통과 후** 스테이징 파일을 최종 경로 `<원본PDF폴더>_md/<input>.md`로 복사한다. 대상 디렉토리가 없으면 `mkdir -p`로 생성. 동일 원본 폴더의 다중 PDF는 동일한 `<원본폴더>_md/`에 누적 저장.

8. **최종 경로 검증 및 정리** (점유한 파일 단위)
   - **경로 검증**: 이번 실행이 점유했던 모든 PDF에 대해 다음을 확인한다.
     - `<원본PDF폴더>_md/<input>.md` 존재, 크기 > 0.
     - `<원본PDF폴더>_md/assets/<input>/` 이미지 개수가 서브에이전트 완료 보고의 `추출_이미지_수` 합계와 일치.
     - 최종 `.md` 내 모든 이미지 링크가 `test -f` 기준으로 실제 파일을 가리킴.
     - 해당 파일의 모든 구간이 `sessions/<session_id>/done/<input>/`에 존재(실패 항목은 `sessions/<session_id>/failed/<input>/`로 분리되어 보고됨).
   - **파일 단위 정리**: 검증을 통과한 파일마다 다음을 **이 순서대로** 수행한다.
     1. `<workroot>/queue/sessions/<session_id>/{pending,working,done,assets}/<input>/`를 `rm -rf`로 삭제.
     2. `<workroot>/queue/sessions/<session_id>/out/<input>.md`를 삭제.
     3. `<workroot>/queue/sessions/<session_id>/pdf_parts/<input>__part*.pdf`를 삭제.
     4. **마지막에** `<workroot>/queue/locks/<input>.lock` 파일을 `os.unlink`(또는 쉘 `rm <workroot>/queue/locks/<input>.lock`, **`rm -rf` 금지**)로 삭제하여 락을 해제한다. **순서 엄수**: 큐·자산 정리 전에 락을 해제하면 다른 오케스트레이터가 절반만 정리된 상태를 점유해 손상된 큐를 읽을 수 있으므로 반드시 이 순서를 지킨다.
   - **다른 파일 보존**: 이번 실행이 점유하지 않은 파일(다른 오케스트레이터가 사용 중일 수 있음)의 큐·락·자산은 **절대 건드리지 않는다**.
   - **라스트 원 클린업**: 모든 파일 정리 후 `<workroot>/queue/sessions/<session_id>/{pending,working,done,assets,pdf_parts,failed,out}/`가 모두 비어 있으면 `rmdir` 시도로 빈 디렉토리를 제거한다. 세션 디렉토리 자체(`sessions/<session_id>/`)도 비어 있으면 `rmdir`로 제거한다. `locks/`는 글로벌이므로 별도 판정한다(실패는 무시).
   - **검증 실패 시 절대 삭제하지 않는다.** 실패 원인을 보고하고 해당 파일의 큐·락을 보존한다. 락 파일은 **atomic replace 규약**으로 `state=failed`로 갱신하여 사용자에게 수동 복구 대상임을 명시한다.

### 3.3 조건 플래그 확정 규칙

분해(절차 4) 시점에 각 파트에 대해 다음 값을 산출하여 task.json과 프롬프트 슬롯(4.2)에 주입한다.

| 플래그 | 타입 | 산출 방법 |
|---|---|---|
| `part_index` | 문자열 | `01`, `02`, … `NN` (분할 순서, 2자리 zero-pad) |
| `total_parts` | int | `ceil(total_pages / 50)` (최대 40) |
| `is_first_part` | bool | `part_index == "01"` |
| `is_last_part` | bool | `part_index == total_parts` |
| `is_single_part` | bool | `total_parts == 1` |

**사전 플래그가 아닌 것들**:

- **`images_in_range`는 사전 플래그가 아니다.** 서브에이전트가 런타임에 `part_source`를 직접 읽어 이미지 존재 여부와 개수를 판단하고, 추출된 이미지 수를 완료 보고(서브에이전트 정의 [.claude/agents/pdf2md-worker.md](../../agents/pdf2md-worker.md) "완료 보고 형식" 절)에 포함한다.
- **`has_subscripts`는 사전 플래그가 아니다.** 서브에이전트가 `part_source`를 직접 읽어 첨자 발견 여부를 완료 보고(동 서브에이전트 정의)에 포함하고, 오케스트레이터가 병합 시(절차 6) MD033 disable 디렉티브를 주입한다.
- **`boundary_warning`도 사전 플래그가 아니다.** 오케스트레이터가 병합 시(절차 6) 파트 경계 줄을 직접 검사하여 이어붙인다. 에이전트는 서브에이전트 정의의 불변 변환 규칙에 따라 잘린 문장을 임의 완성하지 않는다.

### 3.4 서브에이전트 프롬프트 조립 규칙

매 Agent 호출마다 다음 조립 절차를 따른다.

1. Agent 호출 시 `subagent_type: "pdf2md-worker"`를 지정한다. 이것으로 `.claude/agents/pdf2md-worker.md`의 시스템 프롬프트(정적 지시문)가 자동 로드된다.
2. 4.1(역할/입력)의 경로 플레이스홀더(`<workroot>`, `<input>`, `<start>`, `<end>`, `partNN`)를 실제 값으로 치환하여 prompt에 포함한다.
3. 4.2(조건 플래그) 슬롯의 각 항목을 3.3에서 확정한 실제 값으로 치환하여 prompt에 포함한다.
4. prompt에 4.1/4.2 외의 정적 지시문(변환 규칙, DO/DON'T 등)을 직접 복사하지 않는다. 서브에이전트 정의에 시스템 프롬프트로 내장되어 자동 주입되므로 압축·잘림이 발생하지 않는다.
5. 템플릿 외부에 추가 지시사항을 덧붙이지 않는다. 문서별 특이사항이 있다면 에이전트가 완료 보고 "특이사항" 항목으로 역보고하게 두고, 병합 단계에서 오케스트레이터가 처리한다.

### 3.5 DO / DON'T (오케스트레이터)

#### DO

- **session_id를 확인**하고 글로벌 락(`open("locks/<input>.lock", "x")` → `O_CREAT|O_EXCL`)으로 파일 단위 배타 점유를 확보한 뒤에만 해당 파일의 큐 적재·실행을 수행한다.
- 폴더 입력 시 `<원본폴더>_md/<input>.md` 존재 여부를 검사하여 변환 완료 파일을 스킵한다. 스킵 목록은 사용자에게 보고하고 `agent_report.md`에도 기록한다.
- 분해 전 `pdfinfo`로 메타데이터를 수집하여 조건 플래그를 정확히 산출한다.
- 파일당 파트 수 ≤ 40, 총 파트 수 ≤ 100 상한을 사전 검증한다.
- 페이지 추출물은 `qpdf --pages`로 단일 파일로 생성한다.
- 서브에이전트가 이미지를 추출할 디렉토리(`<workroot>/queue/sessions/<session_id>/assets/<input>/`)를 사전 생성한다.
- **파일 단위 점유**: `open(<workroot>/queue/locks/<input>.lock, "x")`(`O_CREAT|O_EXCL`)로 원자 점유. 실패(`EEXIST`) 시 다른 오케스트레이터가 선점한 것으로 판단하고 다음 파일로 넘어간다. 상태 갱신은 반드시 same-directory temp file + `os.rename()` 규약을 사용한다(직접 덮어쓰기 금지).
- 큐 이동(`sessions/<session_id>/pending → working → done`, 실패 재투입)은 `mv`로 원자 처리한다.
- 서브에이전트는 `run_in_background: true`로 기동하고 **라운드당 최대 40개를 단일 메시지에서 병렬 호출**한다. 완료 알림 도착 시 즉시 후처리 후 `sessions/<session_id>/working/<input>/` → `sessions/<session_id>/done/<input>/`으로 이동한다.
- 라운드 플래닝은 파트 수 내림차순 그리디 패킹(파일당 파트 ≤ 40, 라운드당 합 ≤ 40, 파일 분절 금지)으로 수행한다.
- 라운드 종료(모든 파트 완료/실패) 후 남은 라운드가 있으면 다음 라운드를 기동한다.
- 서브에이전트 완료 보고의 `첨자 발견` 플래그를 파일별로 누적하여 병합 시 MD033 디렉티브 주입 여부를 결정한다.
- 병합 시 파트 경계 줄을 검사하여 잘린 문단·목록·표를 이어붙인다(내용 변경 없이 구조만 복원).
- markdownlint 설정이 없으면 기본값, 프로젝트에 `.markdownlint.json`이 있으면 그것을 우선한다.
- markdownlint 규칙 가이드는 별도 파일 `.claude/skills/pdf2md/markdownlint_rules.md`에서 상시 갱신·관리한다. 변환 시 참고(서브에이전트) 및 최종 검증(오케스트레이터)의 단일 출처(SSOT)이다.
- 오탈자 검사는 `language_tool_python`으로 en/ko 실행, 단일 후보·오탈자 카테고리 한정 자동 수정, 그 외는 사용자 보고.
- 오탈자 리포트 생성은 필수, 후처리 필터링은 선택이다: `scripts/filter_typo_report.py`와 `shared/typo_whitelist.yaml`이 **둘 다 존재할 때만** `python3 scripts/filter_typo_report.py`로 False Positive를 제거하고, 둘 중 하나라도 없으면 원본 리포트를 그대로 수용한다(스크립트/디렉터리 부재를 스킬 실패로 간주하지 않는다). 파일이 제공된 경우 화이트리스트 SSOT: `shared/typo_whitelist.yaml`.
- 검증 실패 시 해당 파일의 큐·락을 보존한 채(락 `state=failed`) 사용자에게 보고한다.

#### DON'T

- 본문을 사전 텍스트화하여 에이전트에 문자열로 넘기지 않는다(`pdftotext`·`pymupdf`·`pdfminer` 등으로 본문 추출 후 전달 금지).
- 오케스트레이터가 이미지를 사전 추출(`pdfimages`)하지 않는다. 이미지 추출은 서브에이전트 책임이다.
- 서브에이전트 prompt에 정적 지시문을 직접 복사하지 않는다(`subagent_type: "pdf2md-worker"` 지정 시 시스템 프롬프트로 자동 주입된다).
- 한 에이전트에 두 개 이상의 작업을 동시에 점유시키지 않는다.
- 파트 경계 판정에서 내용 자체를 변경하지 않는다(구조 복원만).
- 페이지 단위·경계 마크(`--- page N ---` 등)를 중간·최종 산출물 어디에도 삽입하지 않는다.
- markdownlint 위반을 무시한 채 완료 선언하지 않는다.
- 다중 후보·문맥 의존·문법 카테고리의 오탈자를 임의 자동 수정하지 않는다(원문 의미 변형 위험).
- markdownlint 규칙을 SKILL.md 본문에 재이식하지 않는다. `markdownlint_rules.md`가 유일한 출처.
- **점유하지 않은 파일의 큐·락·자산을 건드리지 않는다.** 다른 오케스트레이터가 사용 중일 수 있다.
- **실패한 파트를 다른 파일 큐나 다음 라운드로 보내지 않는다.** 재시도는 같은 라운드 내부(`sessions/<session_id>/working/<input>/`)에서만 수행한다.
- **1개 파일을 2개 이상의 라운드에 걸쳐 분할 실행하지 않는다.** 파일당 파트 수가 40을 초과하면 사용자에게 물리 분할을 요청한다(승인 우회 불가).
- **라운드당 40개, 전체 실행 100개 상한을 초과하지 않는다.** 총 100건 초과는 사용자 승인을 받고, 파일당 40건 초과는 승인으로도 우회하지 않는다.
- 검증 실패 시 해당 파일의 큐·락을 삭제하지 않는다.

### 3.6 체크리스트 (오케스트레이터)

**초기화 (절차 1~4)**

- [ ] session_id 확인 (현재 Claude Code 세션 UUID)
- [ ] 큐 트리 준비: `<workroot>/queue/locks/` + `<workroot>/queue/sessions/<session_id>/{pdf_parts,pending,working,done,failed,assets,out}/`
- [ ] 폴더 입력 시 기존 산출물 스캔 → 변환 완료 파일 스킵, 스킵 목록 사용자 보고
- [ ] 각 대상 파일 `pdfinfo`로 총 페이지 수 확인 → `ceil(pages/50)` 파트 수 산출
- [ ] 파일당 파트 수 ≤ 40 확인(초과 → 물리 분할 요청 + 제외, 우회 불가)
- [ ] 총 파트 수 ≤ 100 확인(초과 → 사용자 승인 요청 또는 하위 파일 제외)
- [ ] 대상 파일을 **파트 수 내림차순(큰 파일 우선)**으로 정렬
- [ ] 각 대상 파일에 대해 글로벌 락 점유 시도(`open("locks/<input>.lock", "x")` → `O_CREAT|O_EXCL`). 실패(`EEXIST`) → 스킵 및 보고
- [ ] 점유 성공 시 단일 라인 JSON `{"owner":"<session_id>","state":"pending","claimed_at":"<ISO8601>","updated_at":"<ISO8601>"}`를 한 번의 `write()`로 기록
- [ ] `<workroot>/queue/sessions/<session_id>/assets/<input>/` 이미지 출력 디렉토리 사전 생성
- [ ] 각 파트의 조건 플래그(`part_index`, `total_parts`, `is_first_part`, `is_last_part`, `is_single_part`) 확정
- [ ] 각 파트의 `part_source` PDF 추출물을 `queue/sessions/<session_id>/pdf_parts/`에 생성
- [ ] 모든 구간 작업 파일이 `sessions/<session_id>/pending/<input>/partNN.task.json`에 적재됨

**라운드 플래닝 (절차 5.0)**

- [ ] 점유 파일을 파트 수 내림차순으로 정렬
- [ ] 라운드당 파트 합 ≤ 40 그리디 패킹(파일 분절 금지)
- [ ] 라운드 수 ≤ 3 (`ceil(100/40)`) 확인

**라운드 시작 — 서브에이전트 기동 (절차 5a)**

- [ ] 현재 라운드 파일들의 `sessions/<session_id>/pending/<input>/` → `sessions/<session_id>/working/<input>/` `mv` 일괄 이동
- [ ] 락 상태 `working`으로 갱신 (`state="working"` + `updated_at=<현재 ISO8601>` 함께; same-directory temp file + `os.rename()` atomic replace, 직접 덮어쓰기 금지)
- [ ] 4.1/4.2만 prompt에 포함하여 슬롯 치환(정적 지시문은 `subagent_type`으로 자동 로드)
- [ ] 현재 라운드 전체 파트(≤40)를 **단일 메시지**에서 `subagent_type: "pdf2md-worker"` + `run_in_background: true`로 병렬 기동

**완료 처리 (절차 5b, 완료 알림마다 반복)**

- [ ] 완료 보고 파싱, `첨자_발견` 플래그·`추출_이미지_수` 누적
- [ ] 완료된 작업을 `sessions/<session_id>/working/<input>/` → `sessions/<session_id>/done/<input>/`으로 이동
- [ ] 실패 작업은 동일 라운드 내 재시도(카운트 증가), 임계 초과 시 `sessions/<session_id>/failed/<input>/`로 분리
- [ ] 파일별 모든 조각이 `sessions/<session_id>/done/<input>/`에 모이면 **즉시** 절차 6(병합)·절차 7(검증) 수행:
  - [ ] 락 상태 `merging`으로 갱신 (`state="merging"` + `updated_at=<현재 ISO8601>` 함께; atomic replace 규약)
  - [ ] `queue/sessions/<session_id>/out/<input>.md`로 병합, 파트 경계 이어붙임
  - [ ] `첨자_발견: true` 시 `<!-- markdownlint-disable MD033 -->` 주입
  - [ ] 이미지 집계 복사 + 링크 재작성
  - [ ] markdownlint 통과
  - [ ] 오탈자 검사 통과 + FP 필터링 + `agent_report.md` append
  - [ ] 헤딩 순서·계층·번호 표기 원문 일치
  - [ ] 원문 대비 누락 스폿 체크
  - [ ] 최종 경로 배치
  - [ ] 절차 8에 따라 큐·자산 정리 후 락 해제 (5b에서 조기 해제하지 않음)

**다음 라운드 (절차 5c)**

- [ ] 현재 라운드의 모든 파트가 `sessions/<session_id>/done/<input>/` 또는 `sessions/<session_id>/failed/<input>/`에 도달했는지 확인
- [ ] 남은 라운드가 있으면 5a 재수행
- [ ] 더 없으면 절차 8(최종 정리)로 진행

**최종 정리 (절차 8)**

- [ ] 경로 검증: 점유했던 모든 파일에 대해 `<원본폴더>_md/<input>.md` 존재, 이미지 개수 일치, 모든 이미지 링크 해소
- [ ] 사용자 보고 + `agent_report.md` append 완료
- [ ] 검증 통과 파일 단위로 `queue/sessions/<session_id>/{pending,working,done,assets}/<input>/` + `out/<input>.md` + `pdf_parts/<input>__*.pdf` 삭제
- [ ] **마지막에** `queue/locks/<input>.lock` 파일 `os.unlink`(락 해제, `rm -rf` 금지) — 순서 엄수
- [ ] 점유하지 않은 파일의 큐·락은 건드리지 않음
- [ ] 모든 큐 디렉토리가 비었으면 `rmdir` 시도(실패 무시)
- [ ] 검증 실패 시 해당 파일의 큐·락 보존(락 파일 atomic replace으로 `state=failed` 갱신, 삭제 금지)

---

## 4. 서브에이전트 프롬프트 템플릿

> **오케스트레이터 주의**: Agent 호출 시 `subagent_type: "pdf2md-worker"`를 지정하고 프롬프트에는 **4.1(역할/입력)과 4.2(조건 플래그)만 포함**하여 플레이스홀더를 실제 값으로 치환한다. 정적 지시문(핵심 원칙, 변환 절차, 불변 규칙, DO/DON'T, 체크리스트, 완료 보고 형식)은 서브에이전트 정의 파일 `.claude/agents/pdf2md-worker.md`에 시스템 프롬프트로 내장되어 있어 `subagent_type` 지정만으로 자동 주입된다(3.4 참조).

### 4.1 역할 / 입력

```text
역할: PDF 구간을 무손실 마크다운으로 변환하는 전문 에이전트. 이미지 추출·위치 매칭·링크 삽입까지 단독 수행한다.

입력:
- 담당 페이지 추출물 (part_source, 이것만 Read 도구로 직독): <workroot>/queue/sessions/<session_id>/pdf_parts/<input>__partNN.pdf
- 담당 페이지 범위: <start>-<end>
- 이미지 출력 디렉토리 (서브에이전트가 추출한 이미지 저장): <workroot>/queue/sessions/<session_id>/assets/<input>/
- 이미지 파일명 접두사: partNN-fig  (예: pdfimages -all <part_source> <workroot>/queue/sessions/<session_id>/assets/<input>/partNN-fig)
- 출력 파일: <workroot>/queue/sessions/<session_id>/working/<input>/partNN.md
```

### 4.2 작업 조건 (조건 플래그)

```text
작업 조건 (오케스트레이터가 분해 시 확정):
- part_index:      <NN>      (2자리 zero-pad, 예: 01, 02, ..., 40)
- total_parts:     <N>       (정수, 1~40)
- is_first_part:   <true | false>
- is_last_part:    <true | false>
- is_single_part:  <true | false>
```

### 4.3 정적 지시문 (서브에이전트 정의)

서브에이전트의 변환 규칙, 절차, DO/DON'T, 체크리스트, 완료 보고 형식은 Claude Code 서브에이전트 정의 파일의 시스템 프롬프트로 내장되어 있다. 오케스트레이터가 `subagent_type: "pdf2md-worker"`로 Agent를 호출하면 자동 주입된다.

- **파일 경로**: `.claude/agents/pdf2md-worker.md`
- **포함 내용**: 핵심 원칙, 변환 절차, 불변 변환 규칙, 조건부 분기 규칙, markdownlint 참조, DO/DON'T, 자가 체크리스트, 완료 보고 형식

---

## 5. 참조

- 서브에이전트 정의(정적 지시문): `.claude/agents/pdf2md-worker.md`
