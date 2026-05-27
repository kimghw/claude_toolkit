---
description: ".claude/skills/<name>/SKILL.md 가 4절 계약 (`## 산출물` / `## 산출물 명명` / `## 산출물 위치` / `## AskUserQuestion`) 을 지키는지 lint. 절 존재뿐 아니라 **내용 충실도**까지 검사 — 산출물 행 수·명명/위치 필수 행·AskUserQuestion 호출 분기·옵션이 표로 명시됐는지 확인. 기본은 단일 스킬, `--all` 지정 시 전체. `--fix` 시 누락 절·누락 행은 본문/`.py` 코드에서 정보 끌어와 채움 (빈 TODO stub 금지)."
argument-hint: "<skill_name> | --all [--fix] [--dry-run]"
allowed-tools: Bash, Read, Edit, Write, Glob, Grep, AskUserQuestion
---

# /lint_skill 명령

인자: $ARGUMENTS

## 4절 계약

모든 `.claude/skills/<name>/SKILL.md` 는 다음 4절을 **h2 (`## `) 레벨로**, **표 형태**로 포함해야 한다. 표 컬럼·필수 내용 기준은 둘 다 검사한다 — 절이 있더라도 컬럼이 빠지거나 내용이 비어 있으면 `THIN` 으로 잡는다.

| # | 절 제목 | 표 컬럼 | 필수 내용 (최소 기준) |
|---|---|---|---|
| 1 | `## 산출물` | `산출물 \| 생성 조건 \| 후속 사용처` | 스킬이 만드는 산출물마다 **한 행씩**, 각 행 3컬럼 모두 채움. "산출물 0개" 가 의미상 맞는 스킬은 한 줄 "**없음** — 본 스킬은 산출물 없음" 명시. |
| 2 | `## 산출물 명명` | `속성 \| 값` | 다섯 행 모두 존재: **stem 유도** / **suffix** / **확장자** / **사용자 지정 옵션** / **충돌 처리**. "값" 칸이 비어 있거나 `TODO`·`(미확인)` 만 있으면 `THIN`. |
| 3 | `## 산출물 위치` | `속성 \| 값` | 최소 행: **디렉터리 경로** / **원본 보존 여부** / **캐시 공유 (다른 스킬과)** / **경로 오버라이드 (CLI 인자)**. 경로는 구체적이어야 함 (`<skill_dir>/output/` 같은 placeholder OK, 그러나 단순 "출력 폴더" 만 적힌 행은 `THIN`). |
| 4 | `## AskUserQuestion` | `트리거 \| 질문 요지 \| 옵션 \| 기본 권장` | 스킬 코드에서 발견되는 **모든 AskUserQuestion 호출마다 한 행씩**. 각 행: **트리거** (어느 분기 조건에서 묻는지), **질문 요지** (질문 한 줄 요약), **옵션** (선택지 라벨 전부 — `\|` 로 구분하거나 bullet), **기본 권장** (옵션 중 어느 것이 기본 권장인지). 호출이 0개인 스킬만 표 대신 한 줄 "**없음** — 조용히 진행". |

매칭 규칙: 제목 끝 콜론·여분 공백·`(영문)` 부분 무시하고 한글 부분 일치. h3 이하는 `DEMOTED`, 다른 이름 (`## 출력`, `## 산출물 파일명 정책`) 은 `RENAMED`. 절이 표 형태인데 컬럼·행이 부족하면 `THIN`.

## 인자

기본 동작은 **단일 스킬** 검사. 전체 검사는 명시적으로 `--all` 플래그가 필요하다.

| 인자 | 동작 |
|---|---|
| (없음) | `AskUserQuestion` 으로 어느 스킬을 검사할지 묻고 진행. |
| `<skill_name>` | 그 스킬 하나만 검사 (기본 단위). `.claude/skills/<skill_name>/SKILL.md` 가 없으면 에러. |
| `--all` | `.claude/skills/*/SKILL.md` 전체. `.back` 접미사 스킬은 자동 제외. |
| `--fix` | 누락·DEMOTED·RENAMED 보강. 미지정 시 검사·리포트만 (안전 기본). |
| `--dry-run` | `--fix` 결과를 stdout 에만 출력, 파일은 건드리지 않음. |
| `help` / `-h` / `--help` | 본 문서 요약만 출력. |

## 동작

1. **대상 수집** —
   - `<skill_name>` 지정: `.claude/skills/<skill_name>/SKILL.md` 한 개만 (없으면 에러 후 종료).
   - `--all` 지정: `glob .claude/skills/*/SKILL.md` 전체 (`.back` 제외).
   - 인자 없음: `AskUserQuestion` 으로 스킬 선택지 제시.
2. **검사 — 절 존재·레벨·제목** — 각 SKILL.md 에서 4절 h2 위치 확인. 상태 코드:
   - `MISSING` : 절 자체가 없음.
   - `DEMOTED` : `### ` 또는 `#### ` 로 들어가 있음 → h2 승격 필요.
   - `RENAMED` : 비표준 제목 (`## 출력`, `## 산출물 파일명 정책` 등) → 표준명으로 변경 필요.
3. **검사 — 절 내용 충실도** — 각 절이 §"4절 계약" 표의 *필수 내용 (최소 기준)* 컬럼을 만족하는지 확인. 위반 시 `THIN`:
   - `## 산출물` : 스킬 본문·`.py` 출력 경로에서 발견되는 산출물 후보 수보다 표 행 수가 적으면 `THIN`.
   - `## 산출물 명명` : 다섯 필수 행 중 빠진 것, 또는 "값" 칸이 빈/`TODO`/`(미확인)` 행 표시.
   - `## 산출물 위치` : 네 필수 행 중 빠진 것 표시. "값" 칸에 구체 경로·정책 없으면 `THIN`.
   - `## AskUserQuestion` : `.claude/skills/<name>/*.py` 를 grep 해 `AskUserQuestion` / `ask_user_question` / `questions=` 호출 인스턴스 수를 센다. **표 행 수 < 호출 수** 이면 `THIN`. 각 행의 4컬럼 (트리거·질문 요지·옵션·기본 권장) 중 비어 있는 것이 있으면 그 컬럼 명시. 코드에 호출이 0개인데 표가 있거나, 코드에 호출이 있는데 한 줄 "**없음**" 만 적혀 있으면 `MISMATCH`.
4. **결과 표시** 예시:
   ```
   [lint_skill] <skill_name>
     ✓ ## 산출물                 (3 rows, 3 artifacts in code)
     ✗ ## 산출물 명명             MISSING
     ⚠ ## 산출물 위치             DEMOTED (line 44, h3 → h2)
     ⚠ ## AskUserQuestion        RENAMED (line 242, `## 산출물 파일명 정책` → 표준)
     ⚠ ## 산출물 명명             THIN (3/5 rows: suffix, 충돌 처리 누락)
     ⚠ ## AskUserQuestion        THIN (1 row, 2 호출 발견 — `--strip` 분기 누락)
     ✗ ## AskUserQuestion        MISMATCH (코드에 2 호출, 본문은 "없음")
   ```
5. **`--fix` 동작** (지정 시):
   - **MISSING / RENAMED 절 신설·rename**: SKILL.md 본문 전체 + 동일 폴더 `.py` 스크립트를 읽고, frontmatter description / "목적"·"입력·출력"·"인자 형식" 등 본문 절 / argparse `--out` 기본값 / `AskUserQuestion(questions=[...])` 인자 트리에서 정보 추출 → §"4절 계약" 의 컬럼·필수 행 스키마로 표를 만들어 append 또는 in-place 교체. **빈 TODO stub 금지** — 본문/코드에 있는 정보는 직접 끌어와 쓸 것. 정말 못 찾는 칸만 `(미확인)` 으로 두고 보강 필요 표시.
   - **DEMOTED**: 해당 줄의 `###`/`####` 을 `##` 로 교체.
   - **THIN — 누락 행 추가**: `산출물 명명`·`산출물 위치` 의 빠진 필수 행을 표 끝에 행 추가 (기존 행은 건드리지 않음). 값은 코드·본문에서 추출, 없으면 `(미확인)`.
   - **THIN — `## AskUserQuestion` 호출 동기화**: `.py` 의 `AskUserQuestion` 호출에서 `question` / `options` (label·description) / 기본 권장 후보를 파싱해 빠진 행 보강. 트리거는 호출 주변 if/elif 분기 조건 한 줄을 발췌하거나, 함수명·코드 위치 (`<file>:<line>`) 로 대체.
   - **MISMATCH (코드 호출 vs "없음")**: "**없음**" 한 줄을 표로 대체하고 호출별 행 채움.
   - **MISMATCH (표 vs 코드 호출 0개)**: 표를 "**없음** — 조용히 진행" 한 줄로 축소하지 *않는다* — 의도 파악 필요하므로 경고만, 사용자 확인 요청.


## 안전 정책

- frontmatter 와 기존 본문 절대 수정 금지. `--fix` 변경 범위는:
  (a) **누락 절 append** — 파일 끝에 새 h2 절 + 표
  (b) **h3→h2 한 줄 승격** — 헤더 줄만 교체
  (c) **비표준 제목 한 줄 rename** — 헤더 줄만 표준명으로 교체
  (d) **THIN 절에 누락 행 append** — 기존 표 끝에 행 추가 (기존 행 건드리지 않음)
- `--fix` 미지정 시 파일 쓰지 않음.
- 4절이 존재하지만 표가 아니라 bullet/문장으로만 적힌 경우: 경고만, `--fix` 가 자동 변환하지 않음 (본문 구조 깨질 위험). 사용자가 직접 표로 정리해야 함.
- `## AskUserQuestion` `MISMATCH (표 있음, 코드 호출 0개)` 는 `--fix` 가 자동 축소하지 않음 — 표가 의도일 수 있음. 일반 모드에선 사용자 확인.

## 예시

- `/lint_skill md2docx_source` — 한 스킬만 검사 (기본 단위).
- `/lint_skill md2docx_source --fix` — 한 스킬 검사 + 보강.
- `/lint_skill --all` — 전체 검사.
- `/lint_skill --all --fix --dry-run` — 전체 보강 미리보기.

