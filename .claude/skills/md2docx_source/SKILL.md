---
name: md2docx_source
description: source(.md) 전처리 (discover + lint + strip) 전용 스킬. 새 source 의 헤딩·번호 인벤토리를 관찰해 카탈로그를 보강(discover)하고, 넘버링/헤딩 모호성을 검사(lint)하며, 회사 양식과 충돌하는 패턴을 검출·치환(strip)한다. md→docx 변환(convert)은 포함하지 않음.
---

# md2docx_source — source(.md) 전처리 (discover + lint + strip)

## 목적

**마크다운 원고를 전처리한다.** Pandoc 으로 변환하기 전에 source(.md) 의 헤딩·번호 인벤토리를 관찰해 strip 카탈로그가 부족하면 보강하고, 넘버링·헤딩 모호성을 검사하며, 회사 양식과 충돌하는 패턴을 검출·제거한다. 그게 전부다.

- 입력: source.md (마크다운 원고)
- 출력: `<cwd>/md2docx_source/<source_stem>_prep.md` (패턴 적용 사본, 선택) + 검사 리포트 (stdout)
- **md → docx 변환은 본 스킬 범위 밖.** 최종 변환까지 필요하면 [`md2docx`](../md2docx/SKILL.md) 사용.

## 용어 (canonical)

| 용어 | 의미 |
|---|---|
| **source** | 변환 입력 마크다운 |
| **discover** | source 의 헤딩·번호 인벤토리를 관찰해 strip 카탈로그가 잡지 못한 후보를 식별. LLM 이 패턴 제안·검증·등록. |
| **lint** | source 의 넘버링/헤딩 사전 검토. 모호성 감지. |
| **strip** | 회사 양식과 충돌하는 markdown 패턴 검출·치환. |

## 인자 형식

```
python md2docx_source.py <source.md>                  # 기본 — lint + strip 검출
python md2docx_source.py <source.md> --discover       # 패턴 발견 (inventory + diff) 후 종료
python md2docx_source.py <source.md> --skip-lint      # strip 만 검출
python md2docx_source.py <source.md> --apply-strip <pid1,pid2,...>
                                                      # 패턴 적용 → <cwd>/md2docx_source/<source_stem>_prep.md
python md2docx_source.py <source.md> --apply-strip <pid> --out X.md
                                                      # 지정 경로로 저장

# discover 직접 호출 (entry/검증/등록)
python discover.py inventory <source.md>              # heading·번호 인벤토리 출력
python discover.py diff      <source.md>              # 카탈로그 미매칭 후보
python discover.py validate  <entry.json|->          # 제안 entry 의 regex/sample 검증
python discover.py add       <entry.json|->          # validate 통과 후 카탈로그 append
python discover.py self-test                          # 카탈로그 전체 sample 재검증
```

## 산출물 위치

원본 source.md 는 **절대 수정되지 않는다.** 패턴 적용 결과는 **작업 루트(cwd)** 의 `md2docx_source/` 폴더에 접미사 `_prep` 를 붙인 새 파일로 저장된다:

- `<cwd>/md2docx_source/<source_stem>_prep.md` (패턴 적용 사본, `--apply-strip` 시만 생성)

예: `c:\proj` 에서 `report.md` 의 패턴을 적용하면 `c:\proj\md2docx_source\report_prep.md` 생성. 폴더가 없으면 자동 생성. 입력 stem 이 이미 `_prep` 으로 끝나면 (재실행) 파일명에 `_prep` 가 중복으로 붙지 않는다.

---

## 사용 도구

| 도구 | 용도 |
|:---|:---|
| `Bash` | `python .claude/skills/md2docx_source/md2docx_source.py <source.md>` 실행 |

외부 의존성: `markdownlint-cli2` / `markdownlint` / `pymarkdown` (선택, 없으면 내장 fallback).

---

## 호출 예시

```powershell
# 기본 — lint + strip 검출
python .claude\skills\md2docx_source\md2docx_source.py report.md

# lint 무시하고 strip 패턴 적용
python .claude\skills\md2docx_source\md2docx_source.py report.md --apply-strip heading-manual-number,remove-hrule
# → <cwd>\md2docx_source\report_prep.md 생성

# 지정 경로로 저장
python .claude\skills\md2docx_source\md2docx_source.py report.md --apply-strip p1,p2 --out custom.md
```

---

## 작동 원리

### 단계 0: 패턴 발견 (discover) — LLM 이 카탈로그를 보강

새 source 가 들어왔을 때, LLM 이 헤딩·번호 인벤토리를 **관찰**하고 strip 카탈로그가 잡지 못한 후보를 **확인**해, 필요하면 새 패턴을 **제안·검증·등록**한다. 스크립트는 관찰·추출·검증만 한다 — **선정·작성은 LLM 의 판단**.

**Claude 의 처리 절차** — 새 source 를 처음 만나면 (또는 source 의 헤딩·번호 양식이 기존과 다르다 싶으면):

1. `python md2docx_source.py <source.md> --discover` 호출.
   - 내부적으로 `discover.py inventory` + `discover.py diff` 를 순차 실행.
   - inventory 는 heading total/with_manual_number, 번호 separator 종류(`single`/`dot`/`dash`/`mixed`), bold 매뉴얼 번호, 리스트, hrule 등을 JSON 으로 출력.
   - diff 는 현재 카탈로그가 잡지 못한 헤딩·bold 후보를 출력.
2. **모두 카탈로그가 잡음 (`[DISCOVER-CLEAN]`)** → 단계 1 로 진행.
3. **미매칭 후보 있음 (`[DISCOVER-CANDIDATES]`, returncode=3)** → LLM 이 후보를 보고 판단:
   - 후보가 의도적 제외 케이스(예: `**80005-3:2025 ...**` 같은 표준번호) → 패턴 추가 불필요, 단계 1 진행.
   - 후보가 새 종류 충돌 → 새 entry JSON 작성 후 등록 (아래).

**새 패턴 entry 작성·등록 절차:**

```jsonc
// 예: entry.json (heading-manual-number 의 변형이 아닌 새 충돌이라고 가정)
{
  "id": "my-new-pattern",
  "kind": "remove",
  "name": "...",
  "description": "...",
  "reason": "reference 의 어떤 자동 서식과 충돌하는지",
  "pattern": "^...regex...",
  "replace": "\\1",
  "flags": "MULTILINE",
  "sample": { "before": "...", "after": "..." }
}
```

```powershell
# 1) 검증 (regex compile + sample.before 매칭 + before→after 일관성 + backtracking 검사)
python .claude\skills\md2docx_source\discover.py validate entry.json

# 2) 검증 통과 시 카탈로그 append (validate 를 한 번 더 내부에서 돌림)
python .claude\skills\md2docx_source\discover.py add entry.json

# 3) source 재검사 — 이제 카탈로그가 더 잡음
python .claude\skills\md2docx_source\md2docx_source.py <source.md> --discover
```

**판단 기준 (catalog 보강 정책 — [[feedback-md2docx-strip-accumulate]] 참고):**

- 기존 패턴의 **변형** (예: `### 1.5` 만 잡던 게 `### 1-1.` 도 잡아야 함) → 기존 entry 의 regex 만 확장 (새 항목 추가하지 말 것). 이 경우 `discover.py add` 대신 `strip_patterns.json` 직접 편집 후 `discover.py self-test` 로 회귀 확인.
- **새 종류 충돌** → 새 id 로 별개 항목 추가, `discover.py add` 사용.
- 카탈로그가 늘어도 strip 동작은 변하지 않는다 — `strip.py` 는 `--apply-strip` 에 명시된 id 만 적용하므로 **충돌 위험 없음, 늘릴수록 좋은 자산**.

**카탈로그 회귀 방지 — `self-test`:**

```powershell
python .claude\skills\md2docx_source\discover.py self-test
# → 모든 entry 에 대해 sample.before 에 pattern 적용 → sample.after 일치 확인
# → [SELF-TEST-RESULT] OK=N, FAIL=M
```

기존 패턴의 regex 를 확장했을 때는 반드시 self-test 로 sample 이 깨지지 않았는지 확인.

### 단계 1: Markdown lint — 넘버링/heading 사전 검토

convert 직전, `lint.py` 가 source 의 모호한 넘버링/heading 기호를 검출한다.
외부 도구 우선순위: `markdownlint-cli2` → `markdownlint` → `pymarkdown` → 내장 fallback.

검출 대상:

| Rule | 의미 |
|---|---|
| MD001 | heading 레벨 비순차 (h1 → h3 처럼 건너뜀) |
| MD003 | atx (`# H`) 와 setext (`H\n===`) 혼용 |
| MD004 | bullet 기호 혼용 (`-`, `*`, `+` 가 섞임) |
| MD025 | 한 문서에 `# H1` 다수 |
| MD029 | ordered list 번호 비일관 (`1.`,`1.`,`1.` vs `1.`,`2.`,`3.` 혹은 `1)` 혼용) |
| MD030 | 리스트 마커 뒤 공백 수 비일관 |

**Claude 의 처리 절차** — `lint.py` 가 `returncode=2` 로 종료하고 `[LINT-AMBIGUOUS]` 줄이 출력되면:

1. `AskUserQuestion` 으로 사용자에게 어떤 스타일을 사용할지 묻는다.
2. 답에 따라:
   - **수정**: 사용자 답대로 source 를 편집한 뒤 재실행
   - **그대로 진행**: `--skip-lint` 를 붙여 재실행 (`md2docx_source.py <source.md> --skip-lint`)

### 단계 2: 패턴 검출 — 회사 양식과 충돌하는 source 부분

reference 의 자동 서식(heading 자동 번호, 표 자동 캡션 등)과 source 가 **중복되는 부분**을
누적 관리되는 정규식 패턴 카탈로그([`references/strip_patterns.json`](./references/strip_patterns.json))로 검출한다.

`strip.py` 가 source 에서 매칭을 찾으면 패턴별 `[STRIP-MATCH] <id> (N 곳)` 신호와 sample 을 출력하고 `returncode=3` 으로 종료.

**패턴 분류 (`kind` 필드)**

| kind | 의미 | 사용자 선택 옵션 |
|---|---|---|
| `remove` | reference 자동 서식과 중복되는 수동 표기 제거 | "제거" vs "유지" |
| `promote` | bullet/ordered list 마커를 heading 으로 승격해 reference heading 자동 번호 적용 | "heading 으로 승격" vs "마커 유지" |

**promote 패턴의 매칭 범위 — 최하위 heading 직속 리스트만, 승격은 한 단계 아래로 연속**

`promote` 패턴은 **source 의 가장 깊은(가장 # 개수가 많은) heading 직속 리스트** 에만 적용된다. 다른(더 얕은) heading 섹션 아래 리스트는 매칭에서 제외되어 "그대로 리스트"로 유지된다. source 에 heading 이 하나도 없으면 promote 후보도 없다.

승격되는 heading 레벨은 **속한 heading 의 한 단계 아래(deepest+1)** 로 자동 계산된다 — 즉 속해있는 heading 과 연속적이다 (h3 직속 → h4, h4 직속 → h5). 패턴은 `{HEADING}` 토큰만 가지고, strip.py 가 실제 `#` 개수를 결정한다. deepest 가 이미 9 면 더 깊게 갈 수 없으므로 promote 는 자동 제외된다.

이유: 깊은 heading 안에서 등장하는 리스트는 보통 회사 양식의 자동 번호를 받을 자리이지만 (heading 한 단계 아래 = 그 섹션의 하위 항목), 본문 흐름 속의 단순 나열 (얕은 heading 아래 bullet) 은 그대로 두는 게 자연스럽다. 또 사용자에게 매번 "이 리스트는 승격? 유지?" 를 묻지 않도록 후보를 좁혀 잡음을 줄인다.

예: 문서의 deepest heading 이 `### (h3)` 이면 — `###` 직속 bullet/ordered list 만 promote 후보가 되고, 승격 시 `#### (h4)` 로 변환된다. 상위 `#`/`##` 직속 리스트는 그냥 리스트.

**현재 카탈로그**

| id | kind | 정규식 → 치환 | 효과 | 기본 권장 |
|---|---|---|---|---|
| `heading-manual-number` | remove | 숫자 prefix 제거 (`.` / `-` 구분자 모두, 마지막 `.` 선택). `## 1.`, `### 1.5`, `### 1.2.3`, `### 1-1.`, `### 1-2-3` 모두 매칭. | `## 1. 핵심` → `## 핵심`, `### 1-1. 용어` → `### 용어` | **제거** |
| `bold-manual-number` | remove | bold 텍스트 앞 dotted/dashed 다단계 번호 제거 (`**4-3 ...**`, `**3.1 ...**`, `**1-2-3 ...**`). 단일 숫자 `**4 ...**` 는 제외. `:` 가 이어지는 표준번호(`**80005-3:2025 ...**`) 도 안전. | `**4-3 데이터 모델 표준**` → `**데이터 모델 표준**` | **제거** (절번호 중복 시) |
| `promote-bullets-to-subheading` | promote | bullet → `{HEADING}` (deepest+1) | deepest=h3 일 때 `- 항목` → `#### 항목` | 사용자 판단 |
| `promote-ordered-to-subheading` | promote | ordered list → `{HEADING}` (deepest+1) | deepest=h3 일 때 `1. 단계` → `#### 단계` | 사용자 판단 |
| `remove-hrule` | remove | 수평 분리선 제거 | `---` 제거 | **제거** (frontmatter 사용 시 유지) |
| `remove-table-align-markers` | remove | 표 정렬 표기 제거 | `:---:` → `---` | **제거** (셀별 정렬 의도 시 유지) |

**source 는 절대 수정되지 않는다.** 패턴 적용 결과는 작업 루트(cwd) 의 `md2docx_source/` 폴더에 접미사 `_prep` 를 붙인 새 파일로 저장된다 (`<cwd>/md2docx_source/<source_stem>_prep.md`).

**Claude 의 처리 절차** — `strip.py` 가 returncode=3 이면 매칭된 패턴 **각각에 대해** `AskUserQuestion` 호출. `kind` 에 따라 옵션 문구를 맞춘다.

**heading-manual-number 는 항상 검토하고 기본은 "제거" 로 권한다** — reference 가 heading 자동 번호를 박는 양식이므로 수동 번호와 이중으로 찍히는 사고가 가장 잦다. 사용자가 명시적으로 "수동 번호 유지" 라고 하지 않는 한 제거하는 게 안전한 기본값.

`kind=remove` (예: heading-manual-number):
> "`<패턴명>` 이 N 곳에서 매칭됐습니다. 이유: `<reason>`. 예: `<before>` → `<after>`. 제거할까요? (권장: 제거)"
> - 옵션 1: **제거** (기본 권장 — `remove` 패턴은 reference 자동 서식과 중복되는 경우가 대부분)
> - 옵션 2: **유지**

`kind=promote` (예: promote-bullets-to-subheading):
> "`<패턴명>` 이 N 곳에서 매칭됐습니다. 이유: `<reason>`. 예: `<before>` → `<after>`. heading 으로 승격할까요, 마커로 유지할까요?"
> - 옵션 1: **heading 으로 승격**
> - 옵션 2: **마커 유지**

각 패턴 답을 모은 뒤:
- **제거할 패턴이 있음** → 해당 id 들을 쉼표로 묶어 재실행:
  ```
  python md2docx_source.py <source.md> --apply-strip <pid1>,<pid2>
  ```
- **모두 유지** → 그대로 진행 (원본 사용, `_prep` 파일 미생성)

스탠드얼론 사용도 가능:
```
python strip.py <source.md> --apply <pid1> [<pid2>...]
  → <cwd>/md2docx_source/<source_stem>_prep.md 생성, [STRIP-OUT] 경로 출력
python strip.py <source.md> --apply <pid> --out custom.md
  → 지정 경로로 저장
```

---

## 작동 흐름

```
[입력] <source.md>
   ↓
[0] (선택, --discover 시) discover 실행
   ├─ inventory 출력 — heading·번호·bold·list·hrule 통계
   ├─ diff 출력 — 카탈로그 미매칭 후보
   ├─ returncode=0 ([DISCOVER-CLEAN]): 패턴 추가 불필요
   └─ returncode=3 ([DISCOVER-CANDIDATES]): LLM 이 entry 작성 → validate → add
   ↓
[1] lint 실행 (외부 도구 또는 내장)
   ├─ returncode=0: 문제 없음 → 계속
   ├─ returncode=2: 모호성 감지 → AskUserQuestion → 수정 또는 --skip-lint
   └─ returncode!=0: 실행 오류 → 종료
   ↓
[2] strip 검출 (references/strip_patterns.json)
   ├─ returncode=0: 매칭 없음 → 완료
   ├─ returncode=3: 매칭 있음 → AskUserQuestion → --apply-strip 재실행
   └─ returncode!=0: 실행 오류 → 종료
   ↓
[3] (선택) strip 적용
   └─ <source_stem>_prep.md 생성
   ↓
[출력] <source_stem>_prep.md (선택) + 검사 리포트 (stdout)
```

신호:
- `[DISCOVER-...]` — discover 인벤토리/diff/검증/등록 결과
- `[VALIDATE-OK/FAIL]` — discover.py validate 결과
- `[ADD-OK/FAIL]` — discover.py add 결과
- `[SELF-TEST-RESULT]` — discover.py self-test 결과
- `[LINT-...]` — lint 검사 결과
- `[STRIP-...]` — strip 검출·적용 결과

---

## md2docx 와의 관계

본 스킬은 [`md2docx`](../md2docx/SKILL.md) 의 **source 전처리 단계만** 떼어낸 도구다.

| 항목 | md2docx | md2docx_source (본 스킬) |
|---|---|---|
| 입력 | source.md (+ target.docx) | source.md 만 |
| 출력 | output.docx + 중간 산출물 | <cwd>/md2docx_source/<source_stem>_prep.md (선택) |
| 단계 | lint + strip + map + convert + postprocess | **discover (옵션) + lint + strip** |
| 외부 도구 | pandoc (필수) | markdownlint 등 (선택) |
| 명명 규약 | 공유 (동일한 lint/strip 정의) | 공유 |

**언제 어떤 걸 쓰나:**
- 마크다운 원고를 전처리만 하고 싶음 → **md2docx_source**
- 마크다운 + 회사 양식 docx 를 최종 docx 까지 변환하고 싶음 → **md2docx**

---

## 관련 파일

- [`md2docx_source.py`](./md2docx_source.py) — 통합 진입점 (discover/lint/strip 디스패치)
- [`discover.py`](./discover.py) — LLM-driven 패턴 발견·검증·등록 (inventory / diff / validate / add / self-test)
- [`lint.py`](./lint.py) — source 의 넘버링/heading 사전 검토
- [`strip.py`](./strip.py) — 패턴 카탈로그 기반 검출·치환
- [`references/strip_patterns.json`](./references/strip_patterns.json) — 누적 관리되는 정규식 패턴 카탈로그

## 자주 묻는 질문

**Q. 최종 docx 변환도 해주나요?**
→ 본 스킬 범위 밖입니다. convert 까지 필요하면 [`md2docx`](../md2docx/SKILL.md) 를 사용하세요.

**Q. 패턴을 추가할 수 있나요?**
→ **권장됩니다 — 새 source 가 들어올 때마다 적극적으로 보강하세요.** 카탈로그는 누적 자산이고, `strip.py` 는 `--apply-strip` 에 명시된 id 만 적용하므로 패턴이 늘어도 기존 변환 동작은 변하지 않습니다 (충돌 위험 없음). JSON 만 늘리면 코드 변경 없이 자동 로드됩니다.

**LLM-driven 추가 절차 (권장)** — discover.py 가 보조:

1. `python md2docx_source.py <source.md> --discover` — inventory + diff 출력. LLM 이 결과 관찰.
2. LLM 이 미매칭 후보를 보고 새 entry JSON 작성 (필드는 아래 참고).
3. `python discover.py validate <entry.json|->` — regex compile + sample.before 매칭 + before→after 일관성 + catastrophic backtracking 검사.
4. `python discover.py add <entry.json|->` — validate 통과 후 strip_patterns.json 에 append.
5. `python discover.py self-test` — 카탈로그 전체 sample 재검증 (회귀 방지).

**entry JSON 필드:**
- `id` (영문 kebab-case, 전역 유니크)
- `kind` (`remove` 또는 `promote`)
- `pattern` (Python 정규식, JSON 이라 백슬래시 두 번)
- `replace` (치환 문자열, 백레퍼런스는 `\\1`, `\\2`)
- `flags` (선택, `MULTILINE` 등)
- `reason` (사용자가 보고 판단할 근거 — reference 의 어떤 자동 서식과 충돌하는지)
- `sample.before` / `sample.after` (매칭 예시 — 둘 다 기입, 실제 문자 그대로 — `"\\n"` 처럼 escape 하지 말 것, validate 가 실제 적용 결과를 비교함)

**판단 기준:**
- 기존 패턴의 **변형**이면 (예: `### 1.5` 만 잡던 게 `### 1-1.` 도 잡아야 함) → 기존 항목의 regex 만 확장 (분리하지 말 것). 이 경우 `discover.py add` 대신 JSON 직접 편집 후 `discover.py self-test` 로 회귀 확인.
- **새 종류 충돌**이면 → 새 id 로 별개 항목 추가, `discover.py add` 사용.
- 잘 적용된다 싶으면 위 카탈로그 표 "기본 권장" 컬럼도 같이 갱신.

**Q. 특정 패턴을 항상 적용하고 싶습니다.**
→ `--apply-strip` 에 패턴 id 를 지정하세요. 또는 기본값으로 적용되게 하려면 [`md2docx`](../md2docx/SKILL.md) 의 `--apply-strip` 옵션과 함께 사용하세요.


## 산출물

| 산출물 | 생성 조건 | 후속 사용처 |
|---|---|---|
| `<source_stem>_prep.md` | `--apply-strip <pid,...>` 지정 시만 생성 | `md2docx` (convert 입력으로 그대로 사용 가능) |
| 검사 리포트 (stdout) | 매 실행 | LLM 이 `[DISCOVER-*]` / `[LINT-AMBIGUOUS]` / `[STRIP-MATCH]` 시그널을 읽고 후속 행동 결정 |
| `references/strip_patterns.json` (갱신) | `discover.py add` 호출 시 append | 본 스킬 다음 실행, `md2docx` 의 strip 단계 공유 |

원본 `<source.md>` 는 절대 수정되지 않는다.

## 산출물 명명

- **stem 유도**: 입력 `<source.md>` 의 basename 에서 `.md` 확장자를 제거한 부분을 `<source_stem>` 으로 사용. 입력 stem 이 이미 `_prep` 으로 끝나면 (재실행 케이스) 파일명에 `_prep` 가 **중복으로 붙지 않는다** (파일 stem 은 입력 그대로).
- **suffix**: `_prep` 고정 (패턴 적용 사본 표시).
- **확장자**: `.md` 유지.
- **폴더 경로**: `<cwd>/md2docx_source/` (cwd 하위 고정 단일 폴더). 없으면 자동 생성.
- **사용자 지정**: `--out <path>` 로 임의 경로 지정 가능 (단, 원본과 같은 경로는 거부 — strip.py:406).
- **충돌 시**: 같은 경로에 기존 파일이 있으면 **덮어쓰기** (백업 안 함, git 으로 복구).

예: `report.md` → `<cwd>/md2docx_source/report_prep.md`, `electric_report.md` → `<cwd>/md2docx_source/electric_report_prep.md`.

## AskUserQuestion

| 트리거 | 질문 요지 | 옵션 | 기본 권장 |
|---|---|---|---|
| `[LINT-AMBIGUOUS]` — `lint.py` returncode=2 (MD001/003/004/025/029/030 등 모호성 감지) | "넘버링/heading 스타일이 모호합니다. 어떤 스타일로 통일할까요?" | (1) 수정 후 재실행 / (2) 그대로 진행 (`--skip-lint`) | 사용자 판단 (스타일 결정은 도메인 지식) |
| `[STRIP-MATCH] <id>` — `strip.py` returncode=3, `kind=remove` (예: `heading-manual-number`, `bold-manual-number`, `remove-hrule`, `remove-table-align-markers`) | "`<패턴명>` 이 N 곳 매칭됐습니다. 이유: `<reason>`. 예: `<before>` → `<after>`. 제거할까요?" | (1) **제거** (권장) / (2) 유지 | **제거**. 특히 `heading-manual-number` 는 reference 자동 번호와 이중 표기 사고가 잦으므로 사용자가 명시적으로 "유지" 라고 하지 않는 한 제거 ([[feedback-md2docx-strip-heading-number]]). |
| `[STRIP-MATCH] <id>` — `strip.py` returncode=3, `kind=promote` (예: `promote-bullets-to-subheading`, `promote-ordered-to-subheading`) | "`<패턴명>` 이 N 곳 매칭됐습니다. heading 으로 승격할까요, 마커로 유지할까요?" | (1) heading 으로 승격 / (2) 마커 유지 | 사용자 판단 (깊은 heading 직속 리스트만 후보지만 의도 분기 가능). |
| `[DISCOVER-CANDIDATES]` — `--discover` returncode=3, 카탈로그 미매칭 후보 발견 | (질문 아님 — LLM 이 후보를 보고 자체 판단) 새 패턴이 필요한가? | (1) 기존 entry regex 확장 / (2) 새 id 로 add / (3) 의도적 제외 (skip) | LLM 판단 — 묻지 않음. [[feedback-md2docx-strip-accumulate]] 에 따라 새 종류 충돌이면 적극 추가. |
