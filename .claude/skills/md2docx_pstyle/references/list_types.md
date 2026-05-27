# list 그룹 분류 + 마커 카탈로그

`md2docx_pstyle/scan.py` 가 output 의 list 단락(`<w:numPr>` 보유)을 묶을 때 쓰는 분류 키와, AskUserQuestion 에서 사용자에게 제시할 마커 후보의 카탈로그.

본 문서는 **업데이트 가능한 참조**다. 새 lvlText 패턴이나 사용자 양식에서 학습되는 마커가 늘어나면 이 파일을 갱신하면 된다 (scan.py 코드는 그대로 두고).

---

## 1. list 그룹 키

```
key = (numFmt, lvlText, ilvl)
```

| 요소 | 의미 | 예시 |
|---|---|---|
| `numFmt` | `<w:numFmt w:val="...">` — Word 가 인식하는 번호 형식 종류 | `bullet`, `decimal`, `upperRoman`, ... |
| `lvlText` | `<w:lvlText w:val="...">` — 실제 렌더링되는 문자/패턴. `%1` `%2` 는 해당 ilvl 의 자동 번호 placeholder | `•`, `□`, `%1.`, `(%1)`, `%1)` |
| `ilvl` | 중첩 깊이 (0 = 최상위) | `0`, `1`, `2`, ... |

**세 요소가 모두 같아야 같은 그룹.** pandoc 이 같은 markdown 리스트라도 별개 `numId` 를 부여하므로 numId 로 묶으면 결정 부담이 크다. 본 키로 묶으면:
- 같은 `•` bullet 이 본문에 여러 군데 흩어져 있어도 한 그룹
- 같은 `1./2./3.` ordered 도 여러 군데 흩어져 있으면 한 그룹
- 다만 `•` 와 `□` 처럼 lvlText 가 다르면 분리, ilvl=0 과 ilvl=1 도 분리

---

## 2. numFmt 카탈로그 (OOXML 표준)

| numFmt | 의미 | 자주 보는 lvlText |
|---|---|---|
| `bullet` | 글머리 기호 (자동 번호 없음) | `•` (``), `□`, `○`, `▪`, `-`, `*`, `◦` |
| `decimal` | 1, 2, 3 | `%1.`, `(%1)`, `%1)` |
| `decimalZero` | 01, 02, 03 | `%1.` |
| `upperRoman` | I, II, III | `%1.`, `(%1)` |
| `lowerRoman` | i, ii, iii | `%1.`, `(%1)` |
| `upperLetter` | A, B, C | `%1.`, `(%1)`, `%1)` |
| `lowerLetter` | a, b, c | `%1.`, `(%1)` |
| `decimalEnclosedCircle` | ①, ②, ③ | `%1` |
| `decimalFullWidth` | １, ２, ３ (전각) | `%1.` |
| `ideographDigital` | 一, 二, 三 (한자 숫자) | `%1.` |
| `chosung` | ㄱ, ㄴ, ㄷ | `%1.` |
| `ganada` | 가, 나, 다 | `%1.`, `(%1)` |
| `none` | 번호 없음 (스타일만) | `` (빈 문자열) |

새 numFmt 가 발견되면 이 표에 추가.

---

## 3. lvlText 패턴 - 자주 보는 한국 문서 양식

| lvlText | 표시 예 | 비고 |
|---|---|---|
| `%1.` | `1.`, `2.`, `3.` | 가장 흔함 |
| `(%1)` | `(1)`, `(2)`, `(3)` | 한국 공문 양식에서 흔함 |
| `%1)` | `1)`, `2)`, `3)` | 한국 보고서에서 흔함 |
| `제 %1 절` | `제 1 절`, `제 2 절` | 법령·논문 |
| `제 %1 조` | `제 1 조`, `제 2 조` | 법령 |
| `%1.%2` | `1.1`, `1.2`, `2.1` | 멀티레벨 (ilvl=1 의 lvlText) |
| `%1.%2.%3` | `1.1.1` | 멀티레벨 (ilvl=2) |
| `•` (``) | `•` | 기본 bullet (pandoc 기본 출력) |
| `□` | `□` | 한국 양식에서 흔한 bullet |
| `○` | `○` | 한국 양식 보조 bullet |
| `▪` | `▪` | 영문 양식 보조 bullet |
| `-` | `-` | minus 기호를 bullet 로 정의한 양식 |

---

## 3-B. canonical bullet 우선순위

> **SoT (Source of Truth):** [`scan.py`](../scan.py) 의 `CANONICAL_BULLET_PRIORITY` 리스트. 본 §3-B 표는 그 리스트의 mirror — 사람이 읽기 쉽게 두는 사본이고 코드는 보지 않는다. 둘이 어긋나면 코드(상수) 가 이긴다. 우선순위 변경 시 **반드시 둘 다 갱신.**

target 본문에서 학습한 marker 들을 ind 순서가 아니라 **canonical 우선순위** 에 따라 level 번호를 부여한다. target 에 일부만 있으면 해당 level 만 채우고 빈 level 은 hierarchy 에서 누락(skip) — 즉 level 번호는 **canonical position** 을 유지.

| level | marker | 비고 |
|---|---|---|
| 1 | `□` (네모) | 가장 자주 쓰는 최상위 bullet |
| 2 | `○` (동그라미) | 흔한 차상위 bullet |
| 3 | `-` (대시) | 더 깊은 깊이 |
| 4 | `▪` (작은 네모) | |
| 5 | `·` (가운데 점) | |
| 6 | `*` (별) | |
| 7+ | `■` / `●` / `◯` / `◎` / `▫` 등 | 등장 빈도 낮은 marker |

규칙:
- target 본문에 `□` 와 `-` 만 있으면 → hierarchy = `[level 1: □, level 3: -]` (level 2 = ○ 자리는 비어 있음)
- md 의 ilvl=1 (level 2 요구) 이 들어왔는데 hierarchy 에 level 2 가 비어 있으면 → **scan.py 는 자동 fallback 하지 않는다.** Claude (또는 사용자) 가 decisions.json 작성 시 명시적으로 선택해야 함. 보통은 가장 가까운 deeper level (`-`) 의 marker / ppr_inner / marker_rpr 를 복사해 쓰는 게 자연스러움.
- canonical 에 없는 marker (예: 새로 추가된 ❖) 는 priority 끝에 등장 순서대로 → level 12, 13, ...

> **현재 자동화 범위:** `scan.py` 의 `_assign_level()` 은 본문에서 *발견된 마커가 hierarchy 에 있을 때만* level 번호를 부여한다. 없으면 group key 의 level 자리는 `None` 으로 남고, level 빈자리 채움/fallback 은 Claude 책임. 향후 자동 fallback (next deeper available) 을 도입하려면 scan.py 가 group meta 에 `fallback_used: true` 같은 플래그를 노출하도록 확장 필요.

### 두 단계 분리 원칙 (composer 가 decisions.json 만들 때)

1. **우선순위 결정 (md 깊이 기반):** md ilvl=N → priority level = N+1 요구. target hierarchy 에 그 level 있으면 그 marker, 없으면 next deeper available 로 fallback.
2. **마커 스타일 그대로 (target 의 marker 정의 기반):** 결정된 marker 의 `ppr_inner` / `marker_rpr` 를 그대로 decisions.json 에 복사. ind/hanging/leftChars 등 target 정의 값 변경 안 함 — 즉 marker 가 깊이 박혀 있으면 그 깊이 그대로.

이유: target 양식의 marker 정의는 이미 사용자가 의도한 시각적 깊이를 담고 있으므로, level 번호가 아닌 marker 자체의 단락 서식을 따라가는 게 일관성을 유지한다.

코드 상수: [`scan.py`](../scan.py) 의 `CANONICAL_BULLET_PRIORITY` 리스트 — 위 §3-B 헤더 노트 참조 (SoT).

---

## 4. 사용자 양식(target) 의 marker_hierarchy

`scan.py` 가 `target.document.xml` 본문에서 학습한 마커 단락 — `(leading_ws, marker, ind_left, ind_leftChars, ind_hangingChars)` 튜플로 hierarchy 부여. 정렬 기준 `(leftChars asc, left asc)` → level 1, 2, 3 ...

각 사용자 양식마다 마커 hierarchy 가 다르다. **이 카탈로그는 본 프로젝트에서 자주 쓰는 사용자 양식의 마커를 누적하기 위한 표**다.

### doc_sample.docx (2026-05 기준)

canonical priority 적용 결과 — target body 에 `□` 와 `-` 만 있으므로 level 1 + level 3 만 채워짐 (level 2 = ○ 자리는 공석).

| level | marker | leading_ws | leftChars | left | hangingChars | hanging | marker_rPr |
|---|---|---|---|---|---|---|---|
| 1 | `□` | `''` | 0 | 330 | 150 | 330 | `<w:rFonts w:eastAsiaTheme="minorHAnsi"/>` |
| *(2)* | *(○ — target 에 없음)* | | | | | | |
| 3 | `-` | `''` | 200 | 660 | 100 | 220 | `<w:rFonts w:asciiTheme="minorEastAsia" w:hAnsiTheme="minorEastAsia" w:hint="eastAsia"/>` |

> **참고 1:** `-` 마커는 target 자체 정의상 `leftChars=200` + `left=660` 으로 깊이 박혀 있다 (canonical level 3 에 부합). 의도와 다르면 decisions.json 에서 `target_ppr_inner` 를 수동 편집 (예: leftChars 제거).
> **참고 2:** md ilvl=1 (level 2 자리, ○ 가 비었음) 이 들어오면 fallback 으로 가장 가까운 deeper level (`-`) 적용 가능. 또는 사용자가 ○ 를 target 에 추가하면 hierarchy 가 자동으로 level 2 를 채움.

### (다른 사용자 양식 추가 영역)

새 target 으로 작업할 때 scan 결과의 `marker_hierarchy[]` 항목을 여기에 누적. JSON 의 raw 값을 그대로 옮겨두면 나중에 같은 target 재작업 시 빠르게 참조 가능.

---

## 5. AskUserQuestion 의 그룹별 결정 옵션

scan 결과 각 `kind=list` 그룹마다 다음 중 하나를 사용자가 결정. 옵션은 본 카탈로그 + scan 의 `marker_hierarchy` + `list_styles` 에서 자동 도출.

| action | 효과 | 추가 결정 |
|---|---|---|
| `marker` | numPr 제거 + ind 적용 + 마커 문자 단락 앞에 삽입 | `marker_level` (사용자 양식 marker_hierarchy 의 level 번호) — 어느 마커를 쓸지 |
| `list_style` | pStyle 을 사용자 양식의 list_style 로 교체 + numPr 유지 | `target_style_id` (사용자 양식 list_styles 중 하나) |
| `skip` | 무변경 | — |

### 레벨 결정 — 종류별 분리 규칙

**규칙 1 (decimal): action 이 `skip` / `list_style` 일 때 — 우선순위 사전 정의**

`numFmt` 이 `decimal` / `decimalEnclosedCircle` / `upperRoman` / `lowerRoman` / `upperLetter` / `lowerLetter` / `ganada` / `chosung` 등 **자동 번호** 계열이면, 사용자 양식(target) 의 marker_hierarchy 와 무관하게 numbering.xml 의 ilvl 별 lvlText 정의를 그대로 따른다. 별도 level 결정 불필요.

- 이유: decimal 계열은 Word 가 자동으로 번호를 렌더링 → 형식이 numbering.xml 의 `<w:lvl ilvl="N">` 에 박혀 있음
- output 의 ilvl 그대로 사용. md 공백 lookup 불필요.

**예외 (action=`marker`):** 사용자가 decimal 그룹에 대해 `marker` 액션을 명시 선택하면 numbering.xml 의 자동 번호를 버리고 target marker_hierarchy 의 마커를 강제 적용 (규칙 2 의 매핑 규칙 사용). 즉 `1./2./3.` 을 `□/□/□` (또는 ilvl 별 level 마커) 로 일괄 교체.

**규칙 2 (marker/bullet): md 공백 들여쓰기로 결정**

`numFmt` 이 `bullet` (또는 본문 텍스트 마커) 계열이고 target 의 marker_hierarchy 가 **2 레벨 이상**이면, md 의 공백 들여쓰기 → pandoc `<w:ilvl>` → marker_hierarchy 의 동일 번호 level 에 매핑.

```
md_sample.md            pandoc                 target marker_hierarchy
- top item        →     ilvl=0          →     level 1 marker (예: □)
  - nested        →     ilvl=1          →     level 2 marker (예: -)
    - deeper      →     ilvl=2          →     level 3 marker (없으면 fallback)
```

- target marker_hierarchy 가 1 레벨뿐이면 → 자동으로 그것 적용 (결정할 게 없음)
- target marker_hierarchy 가 output ilvl 보다 얕으면 → **Claude 가 decisions.json 작성 시 직접 매핑.** 보통 가장 깊은 level 의 marker 를 fallback 으로 쓰지만, scan.py 는 자동 처리하지 않음 (위 §3-B 의 자동화 범위 노트 참조)

**doc_sample.docx 의 경우:** marker_hierarchy = {level 1: `□`, level 2: `-`} → 2 레벨이므로 규칙 2 적용
- md 의 `- top` (공백 0) → ilvl=0 → level 1 → `□`
- md 의 `  - nested` (공백 2) → ilvl=1 → level 2 → `-`

### list_style 옵션 도출 — `list_styles` 가 1개뿐이면 자동, 여러 개면 사용자 선택

- doc_sample.docx 의 경우: `List Paragraph` (id=a6) 만 있으므로 옵션 1개 → 자동 적용 가능
- 일반 사용자 양식엔 `List Paragraph`, `List Number 1`, `List Bullet 1` 등 여러 개일 수 있음

---

## 6. 분류 우선순위 (scan.py 계약)

한 단락이 동시에 여러 조건을 만족할 수 있는 hybrid 라도 다음 순서로 **하나의 kind 만** 부여.

```
heading → list → marker → list_styled → standard → styled → plain
```

본 카탈로그가 다루는 건 `list` (numPr 보유) 와 `marker` (numPr 없이 본문 마커로 시작) 두 종류. 자세한 분류 규칙은 [`../SKILL.md`](../SKILL.md) "분류 결정 우선순위" 절 참조.

---

## 7. 업데이트 절차

1. 새 numFmt 발견 → §2 표에 추가
2. 새 lvlText 패턴 발견 → §3 표에 추가
3. 새 사용자 양식 작업 → §4 에 marker_hierarchy 누적 (scan 결과 복사·붙여넣기)
4. 새 action 추가 필요 → §5 표 + `apply.py` 함께 갱신

scan.py 코드는 카탈로그 변경에 의존하지 않는다 — 코드는 numbering.xml/document.xml 에서 동적으로 추출, 본 카탈로그는 사람이 이해·참조하기 위한 문서.
