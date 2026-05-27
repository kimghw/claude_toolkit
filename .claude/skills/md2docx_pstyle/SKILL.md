---
name: md2docx_pstyle
description: pandoc 으로 만든 input(.docx) 의 **목록단락 + 표준 단락 pStyle** 을 target.docx (회사 양식) 또는 reference.docx (target→reference 변환 산출물) 의 list 스타일(헤딩 제외)로 매핑·정규화하는 orchestrator. scan 으로 styles.xml 에서 list_styles 만 후보로 추출하고 input 의 standard / list_styled 그룹을 식별 → Claude 가 AskUserQuestion 으로 그룹별 target list_style 선택 → apply 가 pStyle 교체. heading inventory / marker hierarchy / numPr list group / styled group 은 컨텍스트로만 보고 (옵션 매핑). md2docx_layout 의 표·페이지 patch 뒤 순차 호출. (이전 md2docx_layout 의 scan_lists/apply_lists 흐름은 본 스킬로 통합되며 폐기.)
---

# md2docx_pstyle — 목록단락 / 표준 단락 ↔ target list 스타일 매핑 orchestrator

## 목적

**input docx 의 `표준` / `목록단락(List Paragraph)` 단락의 pStyle 을 target 의 list 스타일로 매핑.**
자체 변환 로직 없는 **orchestrator** — `scan.py` 와 `apply.py` 를 호출하고, 중간에 Claude 가 `AskUserQuestion` 으로 그룹별 target list_style 을 사용자에게 받는다.

**입력 어휘:**
- `input` = 후처리 대상 docx (보통 `md2docx_layout` 의 출력) — 본 스킬이 정규화하는 대상.
- `target` = 회사 양식 raw docx — 스타일·marker hierarchy 의 source of truth.
- `reference` = `md2docx_target` 이 만든 target → reference 변환 산출물. styles.xml 어휘는 target 과 동일하게 가지므로 scan 의 style source 로 동일하게 쓸 수 있다.
- scan 은 `--target` 또는 `--reference` 중 하나만 받음 (mutually exclusive, 둘 다 styles.xml 동일하게 추출).

**주 매핑 (AskUserQuestion 으로 결정):**
- **target 측 후보**: target.styles.xml 의 `list_styles` (`List Paragraph` / `목록단락` / `List Number` / `List Bullet` 계열) **또는** `standard_styles` (`Normal` / `표준` / `Compact` / `Body Text` 등). **target 의 heading inventory 는 제외.**
- **input 측 대상**: input 의 `standard` 그룹 (Normal/Compact/표준/Body Text 등) + `list_styled` 그룹 (List Paragraph 계열 pStyle, numPr 없음).
- **결정 → apply**: 각 그룹에 대해 `action="rename"` (단순 pStyle 교체) / `action="list_apply"` (pStyle + ind + numPr) / `action="marker_replace"` (pandoc decimal/bullet 을 target marker 로 강제 교체) 중 하나.

`md2docx_layout` 의 표·페이지 patch 와 분리돼 있어 순차 호출.

---

## 파이프라인 내 위치 (순차 처리)

```
[md2docx]          source.md + reference → md2docx_output/<stem>_pandoc.docx
[md2docx_layout]   md2docx_output/...    → md2docx_layout/<stem>_output.docx   (표·페이지만)
[md2docx_pstyle]   md2docx_layout/<stem>_output.docx + target.docx (또는 reference.docx)
                 → in-place 정규화 (헤딩 pStyle + 리스트 pStyle/numPr + 마커 ind)
```

`md2docx_layout` 는 표·페이지 patch 만 담당 (자동 호출). 목록단락 / 표준 단락의 pStyle 매핑은 사용자 결정이 필요하므로 본 스킬이 단독 처리한다. 이전에 `md2docx_layout` 에 있던 `scan_lists.py`/`apply_lists.py` 는 본 스킬로 통합되며 폐기됐다.

**AskUserQuestion 으로 매핑하는 대상 (본 스킬의 주 책임):**

| input 그룹 kind | 매핑 후보 | 결과 action |
|---|---|---|
| `standard` (Normal/Compact/표준/Body Text 등) | target 의 `standard_styles` 또는 `list_styles` 중 택1 또는 skip | `rename` (target_style_id 부착) |
| `list_styled` (List Paragraph 계열 pStyle, numPr 없음) | target 의 `list_styles` 중 택1 또는 skip | `rename` / `list_apply` / `marker_replace` |

**컨텍스트로만 scan 에 노출되는 그룹 (기본 매핑 대상 아님 — 필요 시 보조 액션 가능):**

- `heading` — input 의 `Heading 1` ~ `Heading N`. target heading inventory 가 있어 매핑 가능은 하지만 본 스킬의 주 책임은 아님 (보통 pandoc 이 이미 올바른 Heading style 을 박는다). 보조로 `rename` 가능.
- `list` — `<w:numPr>` 보유 단락 (pandoc 자동 number). 보조로 `list_apply` + `strip_numpr=true` 사용 가능.
- `marker` — 평문이지만 `□ `, `(가) `, `1. ` 등 마커 + 공백으로 시작. marker_hierarchy 가 학습돼 있어 보조로 `marker_ind` 사용 가능.
- `styled` — 위에 안 맞는 명시 pStyle. 보통 skip.

scan 은 위 6종을 모두 보고하지만 **AskUserQuestion 워크플로의 주 경로는 `standard` + `list_styled` 두 종에 한정**된다. 나머지는 정보 제공용.

---

## 용어 (canonical)

| 용어 | 의미 |
|---|---|
| **target** | 회사 양식 raw docx — heading/list 스타일·마커 hierarchy 의 source of truth. `--target` 으로 scan 에 전달. |
| **reference** | `md2docx_target` 이 만든 target → reference 변환 산출물 docx (Pandoc 호환). styles.xml 어휘는 target 과 동일. `--reference` 로 scan 에 전달 (target 과 mutually exclusive). |
| **input** | 정규화 대상 docx (보통 `md2docx_layout` 가 만든 output, 없으면 pandoc 직출력) |
| **heading_inventory** | style source(target 또는 reference).styles.xml 에서 추출한 heading 계열 스타일 (id, name, basedOn) |
| **list_styles** | style source.styles.xml 에서 추출한 List Paragraph 계열 스타일 (목록단락, List Paragraph 등) |
| **standard_styles** | style source.styles.xml 에서 추출한 표준/본문 계열 스타일 (Normal, Standard, 표준, Compact, Body Text 등) |
| **marker_hierarchy** | style source.document.xml 의 마커 단락에서 학습한 (level, marker, ind, 공백) 리스트 |
| **pstyle_usage** | input.document.xml 에서 단락별 (idx, pStyle, has_numPr, marker, ind) 인벤토리 |

---

## 인자 형식 (orchestrator)

| 호출 | 동작 |
|---|---|
| `md2docx_pstyle help` | 사용법 출력 |
| `md2docx_pstyle scan <input.docx> --target <target.docx>` | scan.py 만 호출 (target 기준, decisions.json 생성용) |
| `md2docx_pstyle scan <input.docx> --reference <reference.docx>` | scan.py 만 호출 (reference 기준). `--target` 과 mutually exclusive — 둘 다 styles.xml 동일하게 추출, 둘 중 하나는 필수. |
| `md2docx_pstyle apply <input.docx> <decisions.json>` | apply.py 만 호출 |
| `md2docx_pstyle scan <input.docx> --target <target.docx> --out-report <json>` | 보고서 경로 지정 |
| `md2docx_pstyle apply <input.docx> <decisions.json> --out <patched.docx>` | 별도 출력 경로 |

본 orchestrator 는 scan + apply 를 한 번에 묶지 **않는다** — 사이에 사용자 결정 (AskUserQuestion) 이 필요해서.

---

## 작동 흐름

```
[1] scan.py  input=<input.docx>  (--target=<target.docx> | --reference=<reference.docx>)  --out-report <json>
        ├ style src → heading_inventory[]  (heading 계열 스타일 메타)
        ├ style src → list_styles[]        (List Paragraph 계열 스타일 메타)
        ├ style src → standard_styles[]    (Normal/Standard/표준/본문 계열 스타일 메타)
        ├ style src → marker_hierarchy[]   (마커 + 공백 + ind, level 부여)
        ├ input → input_style_names        (styleId → name 매핑, kind 분류용)
        ├ input → pstyle_usage[]           (단락 enumerate, pStyle/numPr/marker/ind)
        └ md2docx_pstyle/<input_stem>_line.json   (단일 파일 — 재스캔 시 덮어쓰기)

[2] Claude: report 를 읽고 사용자에게 AskUserQuestion 으로 매핑 결정
       그룹별 다음 중 하나:
         (a) action="rename"          → pStyle 을 target_style_id 로 교체
         (b) action="list_apply"      → pStyle 을 target list_style_id 로 + ind 설정
                                         + numPr 제거 (옵션)
         (c) action="marker_ind"      → target hierarchy 의 (level→ind) 적용,
                                         pStyle 변경 없음 (마커 텍스트 유지)
         (d) action="marker_replace"  → numPr 제거 + target marker_hierarchy 의
                                         (pPr/rPr/ind) 그대로 복사 + 마커 문자
                                         run 을 단락 앞에 삽입.
                                         list / list_styled / marker 그룹을
                                         target 양식의 marker 로 강제 교체할 때.
         (e) action="skip"            → 무변경
       → decisions.json 작성

[3] apply.py  <input.docx>  <decisions.json>  [--out patched.docx]
       └ paragraph_indices 컨트랙트는 scan 의
         `re.finditer(r'<w:p\b[^>]*>.*?</w:p>', xml, re.DOTALL)` 순서
```

신호: `[SCAN-LINE]`, `[APPLY-LINE]`.

---

## scan.py 출력 스키마 (schema_version=1)

scan 의 보고서는 style source 어휘에 따라 `"target"` 또는 `"reference"` 키 중 하나만 갖는다 (`--target` 으로 받았으면 `"target"`, `--reference` 로 받았으면 `"reference"`).

```json
{
  "schema_version": 1,
  "input": "md2docx_layout/report_output.docx",
  "target": "targets/company.docx",
  "heading_inventory": [
    {"id":"1","name":"heading 1","basedOn":"a","default":false},
    {"id":"Heading1","name":"Heading 1","basedOn":"1","default":false}
  ],
  "list_styles": [
    {"id":"a6","name":"List Paragraph","basedOn":"a","default":false,"ind_left":720}
  ],
  "standard_styles": [
    {"id":"a","name":"Normal","basedOn":"","default":true},
    {"id":"Compact","name":"Compact","basedOn":"a","default":false}
  ],
  "marker_hierarchy": [
    {"level":1,"marker":"□","ind_left":330,"ind_leftChars":0,"ind_hangingChars":150,
     "leading_ws":"",
     "ppr_inner":"<w:pStyle w:val=\"a6\"/><w:ind w:leftChars=\"0\" w:left=\"330\" w:hangingChars=\"150\" w:hanging=\"330\"/>",
     "marker_rpr":"<w:rFonts w:eastAsiaTheme=\"minorHAnsi\"/>"},
    {"level":3,"marker":"-","ind_left":660,"ind_leftChars":200,"ind_hangingChars":100,
     "leading_ws":"",
     "ppr_inner":"<w:pStyle w:val=\"a6\"/><w:ind w:leftChars=\"200\" w:left=\"660\" w:hangingChars=\"100\" w:hanging=\"220\"/>",
     "marker_rpr":"<w:rFonts w:asciiTheme=\"minorEastAsia\" w:hAnsiTheme=\"minorEastAsia\" w:hint=\"eastAsia\"/>"}
  ],
  "pstyle_usage": [
    {"group_id":"H1","kind":"heading","pstyle":"Heading1","pstyle_name":"Heading 1",
     "paragraph_indices":[0,5,10],"samples":["개요","목적","범위"]},
    {"group_id":"L1","kind":"list","pstyle":"a6","pstyle_name":"List Paragraph",
     "numId":"1","ilvl":"0","paragraph_indices":[30,31,32],"samples":["항목 1","항목 2","항목 3"]},
    {"group_id":"M1","kind":"marker","pstyle":null,"pstyle_name":"","marker":"□","level":1,
     "leading_ws":"","paragraph_indices":[40,50],"samples":["□ 단락 1","□ 단락 2"]},
    {"group_id":"LS1","kind":"list_styled","pstyle":"a6","pstyle_name":"List Paragraph",
     "paragraph_indices":[55,56],"samples":["List Para 단락 (numPr 없음)"]},
    {"group_id":"STD1","kind":"standard","pstyle":"Compact","pstyle_name":"Compact",
     "paragraph_indices":[20,21,23],"samples":["본문 단락"]}
  ]
}
```

`kind` 종류: `heading` / `list` (numPr 보유) / `marker` (numPr 없는 마커 단락) / `list_styled` (목록단락 계열 pStyle, numPr 없음) / `standard` (표준·본문 계열 pStyle) / `styled` (그 외 pStyle) / `plain` (스킵).

### 분류 결정 우선순위 (계약)

한 단락이 동시에 여러 조건을 만족할 수 있는 hybrid 인 경우 다음 순서로 **하나의 kind 만** 부여한다:

```
           ┌─ pStyle name 이 'Heading N' / '제목 N' 매칭?    → heading
           │
단락 →     ├─ <w:numPr> 있음?                                  → list   (본문 마커 글자 유무는 무시)
           │
           ├─ 본문이 마커 글자로 시작?                         → marker
           │
           ├─ pStyle name 이 'List Paragraph'/'목록단락' 매칭? → list_styled  (numPr 없는 List Para)
           │
           ├─ pStyle name 이 'Normal'/'Standard'/'표준' 매칭?  → standard
           │
           ├─ 그 외 pStyle 만 박혀 있음?                       → styled
           │
           └─ 아무 것도 없음                                    → plain (스킵)
```

이유:
- **numPr > marker** — `<w:numPr>` 는 Word 가 자동 번호를 렌더링한다는 *구조적* 선언. 본문에 우연히 마커 비슷한 글자가 박혀 있어도 list 로 본다.
- **heading > numPr** — pandoc 이 헤딩에 numPr 를 같이 다는 경우는 거의 없지만, hybrid 라도 heading 으로 분류.
- **marker > list_styled** — 본문 마커가 박힌 단락은 시각적 의미가 더 직접적. pStyle 만으로 List Paragraph 추정은 numPr 도 마커도 없을 때만.
- **list_styled / standard 명시화** — pandoc 이 reference 의 List Paragraph(목록단락) 스타일을 쓰거나, 본문이 Normal/Compact/BodyText 같은 표준 스타일로 박힌 경우를 사용자가 식별·매핑할 수 있게 별도 kind 로 노출.

pStyle (styleId) → name 매핑은 output 의 자기 styles.xml 에서 자동 추출 (`extract_style_name_map`). styleId 가 `a6` 처럼 의미 없어 보여도 name="List Paragraph" 로 해석돼 list_styled 로 분류된다. 매핑 못 찾으면 styleId 자체를 name 으로 fallback.

apply.py 도 같은 가정을 한다 — 한 단락에는 하나의 decision 만 적용 (decisions 가 같은 idx 를 여러 번 지정하면 마지막이 이김).

---

## decisions.json 스키마 (schema_version=1)

```json
{
  "schema_version": 1,
  "input": "md2docx_layout/report_output.docx",
  "decisions": [
    {"group_id":"H1","paragraph_indices":[0,5,10],"action":"rename",
     "target_style_id":"1", "_note":"target 의 'heading 1' styleId='1'"},
    {"group_id":"L1","paragraph_indices":[30,31,32],"action":"list_apply",
     "target_style_id":"a6","ind_left":720,"strip_numpr":true},
    {"group_id":"M1","paragraph_indices":[40,50],"action":"marker_ind",
     "ind_left":0,"ind_leftChars":0,"ind_hangingChars":0},
    {"group_id":"L2","paragraph_indices":[60,61,62],"action":"marker_replace",
     "marker":"□","leading_ws":"",
     "ind_left":330,"ind_leftChars":0,"ind_hangingChars":150,
     "target_ppr_inner":"<w:pStyle w:val=\"a6\"/><w:ind w:leftChars=\"0\" w:left=\"330\" w:hangingChars=\"150\" w:hanging=\"330\"/>",
     "target_marker_rpr":"<w:rFonts w:eastAsiaTheme=\"minorHAnsi\"/>",
     "_note":"pandoc decimal 그룹을 target 의 □ marker 로 강제 교체"},
    {"group_id":"LS1","paragraph_indices":[55,56],"action":"list_apply",
     "target_style_id":"a6","ind_left":720,"strip_numpr":false,
     "_note":"이미 List Paragraph 인데 target 의 동일 styleId 로 정규화"},
    {"group_id":"STD1","paragraph_indices":[20,21,23],"action":"rename",
     "target_style_id":"a", "_note":"Compact → target 의 'Normal' styleId='a'"}
  ]
}
```

action 별 동작:

| action | 효과 | 주 사용 kind |
|---|---|---|
| `rename` | `<w:pStyle w:val="target_style_id"/>` 로 set/replace | heading, standard, styled |
| `list_apply` | pStyle 을 target list_style_id 로 set + ind 설정 (선택) + `strip_numpr=true` 면 numPr 제거 | list, list_styled |
| `marker_ind` | pStyle 변경 없이 `<w:ind>` 만 target hierarchy 값으로 set (마커 텍스트는 그대로) | marker |
| `marker_replace` | numPr 제거 + (target `ppr_inner` 통째 복사 또는 ind 만 설정) + 단락 앞에 `<w:r>{leading_ws}{marker} </w:r>` 삽입. target `marker_rpr` 가 있으면 마커 run 의 rPr 로 적용 (`w:color` 자동 제거 → 검정 색) | list, list_styled, marker (pandoc decimal/bullet 을 target marker 로 강제 교체) |
| `skip` | 무변경 | (모든 kind 공통) |

`marker_replace` 의 필드:

- `marker` (필수) — 삽입할 마커 문자 (`□` / `○` / `-` 등). target 의 `marker_hierarchy[].marker` 값을 그대로 복사.
- `leading_ws` — 마커 앞 leading whitespace (보통 `""`). target 의 `marker_hierarchy[].leading_ws` 값.
- `target_ppr_inner` — target 단락 pPr 내부 XML (pStyle / ind / spacing / jc 등). 있으면 단락 pPr 을 통째 교체 (numPr 잔재는 자동 제거). 없으면 `ind_*` 만 설정 (fallback).
- `target_marker_rpr` — target 마커 run 의 rPr 내부 XML (rFonts / sz / b 등). 있으면 삽입할 마커 run 에 적용. `w:color` 자동 제거.
- `ind_left` / `ind_leftChars` / `ind_hangingChars` — `target_ppr_inner` 미지정 fallback 경로의 들여쓰기 값.

scan 결과 `marker_hierarchy[]` 각 entry 가 `ppr_inner` / `marker_rpr` / `leading_ws` / `ind_*` 를 모두 노출하므로, Claude 가 그대로 복사해 decisions.json 에 박으면 된다.

---

## 산출물 파일명 정책

본 스킬은 **여러 버전 관리를 하지 않는다** — 단일 파일을 덮어쓴다.

| 단계 | 파일명 패턴 | 위치 | 정책 |
|---|---|---|---|
| scan 결과 | `<input_stem>_line.json` | `cwd/md2docx_pstyle/` | 같은 input 재스캔 시 덮어쓰기 |
| 사용자 결정 (decisions) | `<input_stem>_line_decisions.json` | `cwd/md2docx_pstyle/` | 사용자/Claude 가 작성 |
| apply 결과 | `<input_stem>.docx` | in-place 또는 `--out` | 기본은 input 을 덮어쓰기 |

예) `report_output.docx` 입력 →
- `md2docx_pstyle/report_output_line.json` (scan)
- `md2docx_pstyle/report_output_line_decisions.json` (사용자 결정)
- `report_output.docx` (apply 후 — in-place, input 경로 그대로)

다른 경로로 분기하고 싶으면 `--out-report` (scan) / `--out` (apply) 로 오버라이드.

> **자매 스킬과의 컨벤션:** `md2docx_source` / `md2docx_target` / `md2docx_layout` 가 모두 `cwd/<스킬명>/` 폴더에 산출하는 것과 동일.

---

## 사용 도구

| 도구 | 용도 |
|:---|:---|
| `Bash` / `PowerShell` | `python .claude/skills/md2docx_pstyle/md2docx_pstyle.py ...` 실행 |
| `AskUserQuestion` | scan 보고서를 보고 그룹별 매핑 결정 |

---

## 호출 예시

```powershell
# [1] scan — target 기준
python .claude\skills\md2docx_pstyle\md2docx_pstyle.py scan ^
    md2docx_layout\report_output.docx --target targets\company.docx

# (또는) reference 기준 — md2docx_target 의 산출물을 쓸 때
python .claude\skills\md2docx_pstyle\md2docx_pstyle.py scan ^
    md2docx_layout\report_output.docx --reference md2docx_target\company_reference.docx

# [2] Claude 가 출력된 report 를 읽고 사용자에게 AskUserQuestion 으로 그룹별 매핑 받음
#     → md2docx_pstyle\report_output_line_decisions.json 작성

# [3] apply
python .claude\skills\md2docx_pstyle\md2docx_pstyle.py apply ^
    md2docx_layout\report_output.docx md2docx_pstyle\report_output_line_decisions.json
```

직접 호출도 가능:

```powershell
python .claude\skills\md2docx_pstyle\scan.py   md2docx_layout\report.docx --target target.docx
python .claude\skills\md2docx_pstyle\scan.py   md2docx_layout\report.docx --reference md2docx_target\company_reference.docx
python .claude\skills\md2docx_pstyle\apply.py  md2docx_layout\report.docx decisions.json --out final.docx
```

---

## 관련 파일

- [`md2docx_pstyle.py`](./md2docx_pstyle.py) — orchestrator (help + scan/apply subcommand 분기)
- [`scan.py`](./scan.py) — target inventory + output pstyle_usage → JSON
- [`apply.py`](./apply.py) — decisions.json → docx patch
- [`references/list_types.md`](./references/list_types.md) — list 그룹 분류 키 `(numFmt, lvlText, ilvl)` 정의 + numFmt/lvlText 카탈로그 + 사용자 양식별 marker_hierarchy 누적 + md 공백 ↔ ilvl ↔ marker level 매핑 규칙. **업데이트 가능 — 새 패턴 발견 시 갱신.**

## 자주 묻는 질문

**Q. 이전 md2docx_layout.scan_lists/apply_lists 흐름은?**
→ 본 스킬로 통합되며 폐기됐다. 헤딩/리스트/마커 정규화는 모두 `md2docx_pstyle` 사용. 외부 스크립트(자동화 파이프라인 등) 에서 옛 호출 경로를 참조하고 있다면 `python md2docx_pstyle.py scan ... → apply ...` 로 마이그레이션 필요.

**Q. target 의 List Paragraph 스타일이 여러 개면?**
→ scan.py 가 `list_styles[]` 에 모두 노출, AskUserQuestion 에서 사용자가 선택.

**Q. input 에 헤딩이 6단계인데 target 에는 4단계만 있으면?**
→ scan 보고서에 그대로 노출. 사용자가 `Heading 5/6` 그룹을 target 의 어떤 레벨 (또는 일반 본문) 로 매핑할지 결정.

**Q. `--target` 과 `--reference` 차이는?**
→ 둘 다 styles.xml + document.xml 에서 동일하게 추출 — 어떤 걸 줘도 결과 보고서 내용은 같다 (메타 키만 `"target"` vs `"reference"`). `target` = 회사 양식 raw, `reference` = `md2docx_target` 이 그것을 Pandoc 호환으로 변환한 산출물. orchestrator 가 reference 만 손에 들고 있을 때 (예: `md2docx` 파이프라인이 reference 를 만들어 넘기는 경우) `--reference` 를 그대로 패스, target 을 받았으면 `--target` 패스. 둘 다 동시 지정은 mutually exclusive 로 차단.
