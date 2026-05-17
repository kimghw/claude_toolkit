---
name: md2docx
description: Markdown(.md)을 회사 양식의 Word(.docx)로 변환. 단일 진입점 md2docx.py가 인자(파일 확장자)로 자동 분기 — docx만 주면 매핑만 수행해 template/<원본>_mapped.docx 로 저장, md+docx 주면 매핑 후 변환, md 만 주면 template/ 목록 출력 후 사용자 선택. --verify로 XML/PDF 검증. 회사 reference와 Pandoc 어휘 불일치(heading 1 vs Heading 1, Quote vs Block Text 등)는 SEMANTIC_HINTS/STUB_DEFINITIONS로 자동 매핑. reference 의 pseudo-list(□/◌/-/①/(1)/가. + 수동 들여쓰기) 패턴은 두 파일로 분리 관리: (1) template/userlist-<label>.json = per-reference cluster 카탈로그 (userlist_extract.py 가 표준 스타일 단락 관찰 + LLM induction + 사용자 확인 후 Claude 가 작성), (2) <output_dir>/userlist-mapping.json = per-conversion list_kind→cluster_id 매핑 (userlist_scan_lists.py 가 pandoc 출력 numPr 리스트를 (numFmt,ilvl) 별로 dump + 사용자 확인 후 Claude 가 작성). 후자가 존재하면 다음 변환 시 reuse/fresh 를 사용자에게 묻는다. postprocess_userlist.py 가 두 파일을 함께 받아 변환 결과의 numPr 리스트를 해당 cluster 패턴으로 재작성.
---

# md2docx — Markdown → DOCX 통합 파이프라인

## 인자 형식

단일 진입점 `md2docx.py`가 파일 확장자로 자동 분기:

| 호출 | 동작 |
|---|---|
| `md2docx help` (또는 `-h`, `--help`, 인자 없음) | 사용법 출력 |
| `md2docx template <ref.docx>` | **reference 추출(매핑)만** — `template/reference-<label>.docx` 생성 |
| `md2docx <ref.docx>` | (하위 호환) 위와 동일 — 매핑만 |
| `md2docx <input.md>` | **template 선택 요청** — template/ 목록 출력, returncode=4. Claude 가 AskUserQuestion 으로 사용자에게 묻고 `--template <이름>` 으로 재실행 |
| `md2docx <input.md> --template <이름>` | **template/ 에서 선택 후 변환** — 매핑 단계 스킵 |
| `md2docx <input.md> <ref.docx>` | **[기본] 자동 cached/fresh** — `template/reference-<label>.docx` 와 `<output_dir>/userlist-mapping.json` 이 **둘 다** 존재하면 cached (lint/strip/userlist 질문 자동 스킵, 매핑도 스킵). 캐시가 없으면 fresh (매핑부터 모든 사용자 선택 진행) |
| `md2docx renew <input.md> <ref.docx>` | **모든 사용자 선택 재진행** — 캐시 무시, 매핑·lint·strip·userlist 질문 모두 다시 묻는다 |
| `md2docx <input.md> <ref.docx> --verify` | 위 + XML/PDF 검증 |

### 산출물 위치 규칙

**mapped reference 는 항상 skill 의 `template/` 폴더에 `reference-<label>.docx` 명명으로 누적**된다 (재사용 가능한 pandoc reference 카탈로그).

명명 규약 — `label` 은 원본 ref 의 stem 에서 `reference_` 또는 `reference-` 접두사를 제거한 값:
- `reference_reg.docx` → `template/reference-reg.docx` (label=`reg`)
- `reference-foo.docx` → `template/reference-foo.docx` (label=`foo`)
- `company.docx` → `template/reference-company.docx` (label=`company`)

`--template <이름>` 은 label(`reg`), 전체 stem(`reference-reg`), 파일명(`reference-reg.docx`) 모두 허용. 옛 규약 `reference_reg_mapped.docx` 도 호환 (있을 때만 폴백).

`<input.md>` 가 주어지면 그 외 산출물은 **`<cwd>/<template_stem>/<md_stem>/` 폴더 안**에 생성된다:
- `<input>.docx` — 변환 결과
- `<input>_stripped.md` — strip 패턴 적용 사본 (`--apply-strip` 시)
- `_mapping-report.md` — 매핑 분석 리포트
- `verify_out/` — `--verify` 시 검증 산출물

예: `report.md` 를 `reference_reg` template 으로 변환하면 `<cwd>/reference_reg/report/` 폴더가 생성되고 그 안에 위 파일들이 떨어진다. `template_stem` 은 매핑된 reference 의 stem 에서 `_mapped` 접미사를 뺀 값. 같은 cwd 에서 여러 template × 여러 md 변환을 섞어 돌려도 산출물이 폴더로 격리된다. 입력 md 는 어디에 있어도 원본은 보존된다.

매핑-only 모드(`md` 없이 `ref.docx` 만)에선 `<ref>_mapped.docx` 와 `_mapping-report.md` 가 함께 `template/` 안에 떨어진다.

옵션:

| 플래그 | 설명 |
|---|---|
| `--template <이름>` | `template/` 폴더의 매핑된 reference 를 선택. stem(`reference_reg`), `_mapped` 포함 stem, 또는 전체 파일명 모두 허용. `<ref.docx>` 와 동시 지정 불가 |
| `--verify` | verify.py 호출해 XML + PDF 비교 |
| `--skip-lint` | markdown lint(넘버링/heading 사전 검토) 건너뛰기 |
| `--skip-strip` | 패턴 검출(`references/strip_patterns.json`) 단계 건너뛰기 (모두 유지) |
| `--apply-strip <pid1,pid2,...>` | 선택된 패턴을 원본에 적용(원본은 보존, `<md_stem>_stripped.md` 생성)한 뒤 그것을 입력으로 변환 |
| `--no-postprocess` | 변환 후 표 디자인 + 페이지 레이아웃 post-processing 모두 건너뛰기 (기본은 활성) |
| `--min-col-cm <N>` | (postprocess 옵션) 모든 표 칼럼/셀(dxa) 너비를 이 값(cm) 이상으로 강제 — 기본 1.0, `0` 으로 끄기 |
| `--skip-userlist` | 사용자 정의 리스트 관찰·스캔·매핑 단계 모두 건너뛴다 (이미 만들어진 mapping 이 있으면 후처리 적용은 유지) |
| `--no-userlist` | 관찰·스캔·매핑·후처리 적용 모두 비활성 — 이번 변환 한정 |
| `--reuse-userlist-mapping` | `<output_dir>/userlist-mapping.json` 이 존재할 때 묻지 않고 재사용 |
| `--fresh-userlist-mapping` | `<output_dir>/userlist-mapping.json` 삭제 후 새로 스캔/매핑 진행 |
| `--out <file>` | 변환 결과 경로 덮어쓰기 |

`<ref.docx>` 이름이 이미 `_mapped`로 끝나면 매핑 단계 자동 생략.

### Template 선택 흐름 (returncode=4)

`md` 만 주어지고 `--template` 도 없으면 `md2docx.py` 는 `template/*.docx` 목록을 다음 형식으로 stdout 에 출력하고 returncode=4 로 종료한다:

```
[TEMPLATE-LIST] 사용 가능한 template 목록:
[TEMPLATE-OPTION] reference_reg_mapped.docx
[TEMPLATE-OPTION] other_company_mapped.docx
```

**Claude 의 처리 절차** — returncode=4 면:

1. `AskUserQuestion` 으로 사용자에게 묻는다: "변환에 사용할 회사 template 을 골라주세요." 옵션은 `[TEMPLATE-OPTION]` 줄의 파일명들.
2. 사용자가 선택한 stem 으로 재실행:
   ```
   python md2docx.py <input.md> --template <선택된_이름>
   ```
3. `template/` 가 비어 있으면 (`ERROR: template/ 폴더가 비어 있습니다.`) 사용자에게 `<ref.docx>` 위치를 묻고 `md2docx <ref.docx>` 로 먼저 매핑하도록 안내.

---

## 사용 도구

| 도구 | 용도 |
|:---|:---|
| `Bash` | `python .claude/skills/md2docx/md2docx.py ...` 실행 |
| `Read` | 변환 결과 docx/PDF 검토 |
| (외부 CLI) | `pandoc` (필수), `docx2pdf` (verify 시, Windows+MS Word) |

---

## 호출 예시

```powershell
# 사용법
python .claude\skills\md2docx\md2docx.py help

# 새 회사 양식 받았을 때 — 매핑만 (template/ 에 누적)
python .claude\skills\md2docx\md2docx.py company.docx
# → .claude\skills\md2docx\template\company_mapped.docx 생성

# 일상 변환 — template 선택 (Claude 가 사용자에게 묻고 --template 으로 재실행)
python .claude\skills\md2docx\md2docx.py report.md
# → template/ 목록 출력 + returncode=4

# 일상 변환 — 명시적 template 지정
python .claude\skills\md2docx\md2docx.py report.md --template reference_reg
# → template/reference_reg_mapped.docx 로 report.docx 생성

# 일상 변환 — ref.docx 직접 지정 (매핑부터 새로 수행)
python .claude\skills\md2docx\md2docx.py report.md company.docx
# → template/company_mapped.docx 생성 후 report.docx 변환

# 변환 + 시각 검증
python .claude\skills\md2docx\md2docx.py report.md --template reference_reg --verify
```

---

## 작동 원리

### 단계 1: 매핑 (`map.py` 자동 호출)

회사 reference.docx의 스타일에 Pandoc 어휘를 `basedOn` 상속으로 추가. 회사 양식은 그대로 유지.

```xml
<!-- 회사 원본 (그대로) -->
<w:style w:styleId="1"><w:name w:val="heading 1"/>...</w:style>

<!-- map.py가 추가 -->
<w:style w:styleId="Heading1" w:customStyle="1">
  <w:name w:val="Heading 1"/>
  <w:basedOn w:val="1"/>
</w:style>
```

### 매핑 우선순위 (`find_mapping`)

1. user_override (`--map` JSON)
2. exact (이미 일치)
3. case_mismatch (대소문자만 다름)
4. semantic (`SEMANTIC_HINTS` 의미 매칭)
5. stub (`STUB_DEFINITIONS` 디폴트 생성)
6. missing (skip)

자동 매핑 결정 규칙: [`decisions.md`](./decisions.md)

### 단계 1.5: Numbering 인식 — 사용자 확인 필요

회사 reference의 `numbering.xml`에 list 정의(예: `1.`, `①`, `가.`, `제 1)`)가 있으면 `map.py`가 리포트의 "Numbering 정의" 섹션에 표시하고 stdout에 `[NUMBERING]` 신호를 출력한다.

**이때 Claude는 반드시 다음을 수행:**

1. 사용자에게 `AskUserQuestion`으로 묻는다:
   > "회사 reference에 N개 numbering 정의가 있습니다 ([리포트 발췌]). markdown 리스트(`1.`, `2.`, `-`, `*`)에 회사 양식 numbering을 적용하시겠습니까?"
   - 옵션 1: **예 — 회사 numbering 적용** (Word에서 List Paragraph 스타일에 numId 바인딩 안내)
   - 옵션 2: **아니오 — Pandoc 기본 numbering 사용** (기본값, 그대로 진행)

2. 응답이 **예**인 경우:
   - 자동 매핑은 현재 제공되지 않음. Word에서 List Paragraph 스타일의 numbering을 회사 정의로 수동 변경 안내.
   - 또는 mapping.json에 `"paragraph": {"List Paragraph": "회사 list 스타일명"}` 추가해 재실행.

3. 응답이 **아니오** 또는 사용자가 numbering 무시를 선호하면 그대로 변환 진행.

이 확인은 **새 reference.docx로 매핑할 때마다 1회** 묻는다. 결과는 작업 메모리에 유지하고 동일 reference 반복 사용 시 재질문하지 않는다.

### 단계 1.55: 사용자 정의 리스트 패턴 관찰 — LLM 패턴 도출 + 사용자 확인 필요

회사 reference 안에 **`<w:numPr>` 없이** 수동으로 마커(`□`, `◌`, `-`, `①`, `(1)`, `가.`, 또는 처음 보는 임의 글리프)와 들여쓰기만으로 만들어진 "pseudo-list" 단락이 있는 경우, pandoc 의 `--reference-doc` 만으로는 그 모양을 재현할 수 없다 (pandoc 은 markdown `-`/`1.` 을 항상 진짜 numPr 리스트로 변환).

**설계 원칙 — 마커 enum 하드코딩 금지**:
Python(`userlist_extract.py`) 은 단지 **관찰자** 역할만 한다. 표준 스타일(Normal/표준/본문) + numPr 없음 단락의 머릿글·들여쓰기·폰트·문단 정보를 raw 로 dump 한다. 어떤 글리프가 리스트 마커인지 / 같은 들여쓰기·폰트끼리 cluster 로 묶을지 / 어떤 cluster 가 prose 인지 같은 모든 판정은 **Claude(LLM) 가 observations 를 보고 직접 induction** 한다. 이 방식은 처음 보는 마커(예: `□`/`◌`/`▶` 등 무엇이든) 도 자동으로 잡아낸다.

**관찰 도구** — `userlist_extract.py`

```
python userlist_extract.py <reference.docx> --out <observations.json>
```

- **cluster dedup**: 같은 (정규화 머릿글 + 들여쓰기 + 폰트 + pStyle + sz) 단락들은 한 cluster 로 압축. 머릿글 정규화 규칙 — 숫자 연쇄→`N`, 라틴 연쇄→`A`, 한글 음절 연쇄→`H` (예: `1.`/`12.`→`N.`, `(1)`→`(N)`, `가.`/`가나.`→`H.`). enclosed alphanumeric(`①②③`)은 정규식에 안 잡혀 별도 cluster 로 남음 — LLM 이 dump 보고 사후 묶음.
- 출력 JSON: `{reference, label, observations: [...]}`. 각 cluster 는 `idx`(첫 등장), `pStyle`, `head_token`, `head_chars`, `head_normalized`, `text`, `alt_samples`, `sample_count`, `sample_indices`, `indent`, `spacing`, `jc`, `rPr`, `pPr_xml`, `rPr_xml`.
- stdout: `[USERLIST-OBS] cluster='<normalized>' | count=<n> | first_idx=<i> | indices=[…] | ind=left=<x>,hanging=<y> | font='<font>' <sz>pt | pStyle='<style>' | text='<sample>' | alt=[…]` + `[USERLIST-OBS-COUNT] clusters=<m> samples=<n>` + `[USERLIST-OUT] <abs path>`.
- returncode: cluster 0건 = 0, 1건 이상 = 5.

**저장 위치 — 두 파일로 관심사 분리**:

| 파일 | 위치 | 역할 | 작성 시점 |
|---|---|---|---|
| `template/userlist-<label>.json` | skill | **per-reference cluster 카탈로그** — 어떤 cluster 정의들이 있는지 (id/marker_sequence/indent/spacing/jc/rPr/pPr_xml/rPr_xml). `apply_to` 같은 매핑 결정 없음 | 처음 변환 시 단계 1.55, Claude 가 observations 보고 induction + 사용자 확인 후 Write |
| `<cwd>/<template_stem>/<md_stem>/userlist-mapping.json` | per-conversion | **list_kind→cluster_id 매핑** — pandoc 결과의 `(numFmt, ilvl)` 별로 어떤 cluster 를 적용할지 | 단계 2.85, Claude 가 pandoc 스캔 결과 + catalog 보고 사용자 확인 후 Write |

**md2docx.py 단계 1.55** — `<input.md>` 가 함께 주어졌을 때만 동작. 분기:

1. `--no-userlist` 또는 `--skip-userlist` → 모두 건너뜀.
2. catalog 가 없으면 → `userlist_extract.py` 실행 → returncode=5 시 사용자 확인 배너 + `sys.exit(5)`.
3. catalog + mapping 둘 다 존재 → reuse/fresh 분기:
   - `--reuse-userlist-mapping` → 그대로 사용 (단계 2.86 에서 적용).
   - `--fresh-userlist-mapping` → mapping 삭제, 단계 2.85 에서 다시 스캔.
   - 둘 다 없으면 → `[USERLIST-MAPPING-EXISTS]` + 배너 + `sys.exit(6)`.
4. catalog 만 존재 → 단계 2.85 에서 첫 스캔/매핑 수행.

**Claude 의 처리 절차 — 단계 1.55 (catalog 작성, returncode=5 시):**

1. `[USERLIST-OBS]` 줄들을 **직접 보고 induction**:
   - 머릿글 식별 — `head` 필드의 첫 1~3 글자가 무엇인지 (`□`, `◌`, `-`, `①`, `(1)`, `가.`, 또는 임의 글리프).
   - 같은 머릿글 + 같은 들여쓰기(`indent`) + 같은 폰트(`rFonts_ascii`/`rFonts_eastAsia`) 끼리 묶어 cluster 구성.
   - 단발 일회성 강조(`sample_count` 가 1) 나 prose/표 셀로 보이는 cluster 는 제외.
2. 적용 결정 매핑 없이 **cluster 정의만** `template/userlist-<label>.json` 에 Write:

   ```json
   {
     "reference": "reference-reg.docx",
     "label": "reg",
     "clusters": [
       {
         "id": "userlist-□-firstLine440",
         "head_normalized": "□",
         "marker_sequence": ["□"],
         "indent": {"left": null, "hanging": null, "firstLine": "440"},
         "spacing": null,
         "jc": null,
         "rPr": {"rFonts_ascii": "Arial Unicode MS", "sz": null},
         "pPr_xml": "<w:pPr>...</w:pPr>",
         "rPr_xml": "<w:rPr>...</w:rPr>"
       }
     ]
   }
   ```
3. `pPr_xml` / `rPr_xml` 은 `_userlist-<label>-observations.json` 의 해당 cluster 의 raw XML 그대로 복사. `marker_sequence` 는 bullet 형이면 `[글리프]` 하나, ordered 형이면 확장 시퀀스(예: `["①","②",...]`).
4. 작성 후 동일 명령으로 재실행 → catalog 발견 → 단계 1.55 catalog 작성 단계는 자동 스킵, 단계 2.85 에서 mapping 작성으로 진행.

**Claude 의 처리 절차 — 단계 1.55 (mapping 존재, returncode=6 시):**

`AskUserQuestion` 으로 사용자에게 다음 셋 중 하나 묻기:
- **재사용** — `--reuse-userlist-mapping` 추가 후 재실행
- **새로 분석** — `--fresh-userlist-mapping` 추가 후 재실행 (mapping 삭제 + 단계 2.85 재스캔)
- **이번만 비활성** — `--no-userlist` 추가 후 재실행

### 단계 1.6: Markdown lint — 넘버링/heading 사전 검토 (사용자 확인 필요)

pandoc 변환 직전, `lint.py` 가 markdown 원본의 모호한 넘버링/heading 기호를 검출한다.
외부 도구 우선순위: `markdownlint-cli2` → `markdownlint` → `pymarkdown` → 내장 fallback.

검출 대상 (모두 pandoc 출력에서 회사 양식과 충돌 가능):

| Rule | 의미 |
|---|---|
| MD001 | heading 레벨 비순차 (h1 → h3 처럼 건너뜀) |
| MD003 | atx (`# H`) 와 setext (`H\n===`) 혼용 |
| MD004 | bullet 기호 혼용 (`-`, `*`, `+` 가 섞임) |
| MD025 | 한 문서에 `# H1` 다수 |
| MD029 | ordered list 번호 비일관 (`1.`,`1.`,`1.` vs `1.`,`2.`,`3.` 혹은 `1)` 혼용) |
| MD030 | 리스트 마커 뒤 공백 수 비일관 |

**Claude 의 처리 절차** — `lint.py` 가 `returncode=2` 로 종료하고 `[LINT-AMBIGUOUS]` 줄이 출력되면:

1. `AskUserQuestion` 으로 사용자에게 어떤 스타일을 사용할지 묻는다. 예:

   - 넘버링 모호 (MD029): "ordered list 번호를 `1.`,`2.`,`3.` (sequential) 로 통일할까요, 아니면 모두 `1.` 로 둘까요?"
   - bullet 혼용 (MD004): "bullet 기호를 `-`, `*`, `+` 중 어떤 것으로 통일할까요?"
   - heading 혼용 (MD003): "heading 을 모두 atx(`#`) 로 통일할까요, setext(`===`/`---`) 로 둘까요?"
   - h1 다수 (MD025): "최상위 `# 제목` 이 여러 개입니다. 하나만 남기고 나머지는 `##` 로 강등할까요?"
   - heading 비순차 (MD001): "h1 다음에 바로 h3 이 옵니다. 중간에 h2 를 넣을까요, 아니면 h3 을 h2 로 올릴까요?"

2. 답에 따라:
   - **수정**: 사용자 답대로 `.md` 파일을 편집한 뒤 재실행 (`md2docx.py <md> <ref.docx>`)
   - **그대로 진행**: `--skip-lint` 를 붙여 재실행 (`md2docx.py <md> <ref.docx> --skip-lint`)

이 확인은 lint 가 모호성을 감지할 때마다 묻는다. 사용자가 `--skip-lint` 로 진행하기로 한 경우, 같은 파일 재변환 시에도 동일 플래그를 유지한다.

### 단계 1.7: 패턴 검출 — 회사 양식과 충돌하는 markdown 부분 제거 (사용자 확인 필요)

회사 reference 의 자동 서식(heading 자동 번호, 표 자동 캡션 등)과 markdown 원본이 **중복되는 부분**을
누적 관리되는 정규식 패턴 카탈로그([`references/strip_patterns.json`](./references/strip_patterns.json))로 검출한다.

`strip.py` 가 .md 에서 매칭을 찾으면 패턴별 `[STRIP-MATCH] <id> (N 곳)` 신호와 sample(L번호, before, after)을 출력하고 `returncode=3` 으로 종료.

**패턴 분류 (`kind` 필드)**

| kind | 의미 | AskUserQuestion 옵션 형태 |
|---|---|---|
| `remove` | reference 자동 서식과 중복되는 수동 표기 제거 | "제거" vs "유지" |
| `promote` | bullet/ordered list 마커를 heading 으로 승격해 reference heading 자동 번호 적용 | "heading 으로 승격" vs "마커 유지" |

**Reference-aware 필터링** — `md2docx.py` 는 strip.py 를 호출할 때 `--reference <mapped.docx>` 를 함께 넘긴다. `promote-*` 패턴은 `target_heading_level` 필드를 가지며, strip.py 가 reference 의 styles.xml + numbering.xml 을 파싱해 해당 heading 레벨에 numbering 이 **실제로** 정의돼 있는지 확인한다:

- 정의 있음 → 매칭 보고. `reason` 끝에 실제 `lvlText` 포맷(예: `'(1)'`, `'%1.'`)이 주입돼 사용자에게 표시된다.
- 정의 없음 → 그 promote 패턴은 매칭에서 자동 제외 (잘못된 질문 방지).

stdout 신호:
- `[STRIP-HEADING-NUM] reference 의 heading numbering: h5='1.', h6='(%1)'` — reference 에서 발견한 heading numbering 요약.
- `[STRIP-HEADING-NUM] reference 의 heading 스타일에 numbering 정의 없음 (promote 패턴 자동 제외됨)` — heading 에 numbering 이 전혀 없을 때.

**현재 카탈로그**

| id | kind | 정규식 → 치환 | 효과 (reference_reg 기준) |
|---|---|---|---|
| `heading-manual-number` | remove | `^(#+\s+)\d+(?:\.\d+)*\.?\s+` → `\1` | `## 1. 핵심` → `## 핵심` (회사 h2 자동 번호 `제 1 장` 만 남김) |
| `promote-top-bullets-to-h6` | promote | `^(- \|\* \|\+ )` → `###### ` | `- 항목` → `###### 항목` (h6 `(1)(2)(3)` 자동 번호) |
| `promote-top-ordered-to-h5` | promote | `^(\d+)[.)]\s+` → `##### ` | `1. 단계` → `##### 단계` (h5 `1.2.3.` 자동 번호) |
| `remove-hrule` | remove | `^[ \t]*(?:-{3,}\|\*{3,}\|_{3,})[ \t]*\r?\n?` → '' | `---`, `***`, `___` 같은 horizontal rule 줄 통째 제거 (회사 양식은 heading 자동 번호로 구분) |
| `remove-table-align-markers` | remove | 표 구분 줄의 `:` 양쪽 모두 제거 (2-pass) | `\|:---:\|:---\|---:\|` → `\|---\|---\|---\|` (정렬은 회사 Table Grid 가 결정하므로 markdown 표기 불필요) |

`passes` 필드 — 한 패턴 항목이 여러 정규식 패스를 순차 적용하도록 묶을 수 있다 (예: `remove-table-align-markers` 가 `:---` 와 `---:` 두 패스로 구성). 사용자는 한 번의 AskUserQuestion 으로 묶어 답한다.

**원본 .md 는 절대 수정되지 않는다.** 패턴 적용 결과는 같은 폴더에 접미사 `_stripped` 를 붙인 새 파일로 저장된다 (`<원본>_stripped.md`). 출력 docx 는 원본 stem 기준 (`<원본>.docx`).

**Claude 의 처리 절차** — `strip.py` 가 returncode=3 이면 매칭된 패턴 **각각에 대해** `AskUserQuestion` 호출. `kind` 에 따라 옵션 문구를 맞춘다:

`kind=remove` (예: heading-manual-number):
> "`<패턴명>` 이 N 곳에서 매칭됐습니다. 이유: `<reason>`. 예: `<before>` → `<after>`. 제거할까요?"
> - 옵션 1: **제거**
> - 옵션 2: **유지**

`kind=promote` (예: promote-top-bullets-to-h6):
> "`<패턴명>` 이 N 곳에서 매칭됐습니다. 이유: `<reason>`. 예: `<before>` → `<after>`. heading 으로 승격할까요, 마커로 유지할까요?"
> - 옵션 1: **heading 으로 승격** (회사 양식 자동 번호 적용)
> - 옵션 2: **마커 유지** (pandoc 기본 bullet/list)

각 패턴 답을 모은 뒤:
- **제거할 패턴이 있음** → 해당 id 들을 쉼표로 묶어 재실행:
  ```
  python md2docx.py <md> <ref.docx> --apply-strip <pid1>,<pid2>
  ```
  내부적으로 `strip.py --apply` 가 호출되어 `<md_stem>_stripped.md` 가 만들어지고, 그 파일이 pandoc 입력으로 사용됩니다. 원본은 그대로.
- **모두 유지** → `--skip-strip` 추가해 재실행 (원본 .md 가 그대로 pandoc 입력)

스탠드얼론 사용도 가능:
```
python strip.py <md> --apply <pid1> [<pid2>...]
  → <md_stem>_stripped.md 생성, [STRIP-OUT] 경로 출력
python strip.py <md> --apply <pid> --out custom.md
  → 지정 경로로 저장
```

**새 패턴 추가** — `references/strip_patterns.json` 의 `patterns` 배열에 항목 추가:
- `id` (영문 kebab-case), `name`, `description`, `reason`, `pattern`, `replace`, `flags`, `sample` 필수
- JSON 이므로 정규식 백슬래시는 두 번 (`\\d`, `\\s`)
- 결정 사항은 카탈로그에 누적되므로, 다음 .md 변환 시 동일 검사가 자동 적용됨

### 단계 2: 변환 (pandoc 호출)

```
pandoc <input.md> -o <output.docx> --reference-doc=<mapped.docx>
```

### 단계 3: 표 디자인 post-processing (`postprocess_tables.py`)

pandoc 은 `<w:tblPr>` 의 `<w:tblLook>` 을 `0020`(firstRow only) 로 박고 셀에 `cnfStyle` 도 추가하지 않아, reference 의 Table Grid 스타일에 정의된 firstRow/firstCol conditional (주황 `#E97132` / 연하늘 `#C1E4F5`) 채움이 활성화되지 않는다.

`postprocess_tables.py` 가 변환 결과 docx 를 후처리해:

1. 모든 `<w:tblPr>` 의 `<w:tblLook>` → `04A0` (firstRow + firstColumn + noVBand) 로 교체
2. 첫 행 셀에 `cnfStyle firstRow="1"` 추가 (첫 셀은 firstRow + firstColumn)
3. 나머지 행 첫 열 셀에 `cnfStyle firstColumn="1"` 추가
4. 표 셀 단락의 `pStyle="Compact"` 제거 (회사 본문 상속)
5. **표 셀 단락 정렬 (jc) 동기화** — reference 표 스타일의 최상위 `<w:pPr><w:jc/>` (가운데/좌/우) 를 추출해 표 안의 모든 단락에 적용. **이미 `<w:jc>` 가 있는 단락은 유지** — markdown 표의 `:---:`, `:---`, `---:` align 명시로 pandoc 이 박은 jc 가 우선. 단, 단계 1.7 의 `remove-table-align-markers` 패턴이 이 markdown 표기를 제거하므로, 그 패턴을 적용한 경우엔 reference 의 jc 가 모든 표 셀 단락에 일관되게 적용된다 (권장 흐름). 로그: `[POSTPROCESS-PJC] 표 셀 단락에 reference 의 jc='center' 적용`

`--no-postprocess` 로 끌 수 있다 (단계 4·5 도 함께 비활성됨).

### 단계 4: 페이지 레이아웃 동기화 (`postprocess_page.py`)

reference 의 마지막 `<w:sectPr>` 에서 `<w:pgSz>`, `<w:pgMar>`, `<w:cols>`, `<w:docGrid>` 를 추출해 변환 결과 docx 의 **모든 sectPr 에 덮어쓴다**. pandoc 의 `--reference-doc` 가 보통 sectPr 를 복사하지만, 별도 sectPr 가 끼어들거나 reference 가 교체되어도 회사 양식의 페이지 여백·용지 크기·단·격자 설정이 보장된다.

- 로그: `[POSTPROCESS-PAGE]`
- 비활성화: `md2docx.py --no-postprocess` 로 통합 비활성 (단계 3 표 디자인과 함께 꺼짐). 별도 `--no-page-sync` 같은 md2docx.py 인자는 없음.
- 단독 호출도 가능:
  ```
  python postprocess_page.py <docx> --reference <ref.docx>
  ```

### 단계 5: 리스트 단락 속성 강제 적용 (`postprocess_lists.py`)

bullet/머릿기호를 **유지**하기로 한 단락 (= pandoc 이 `<w:numPr>` 를 박은 단락) 에 대해, reference 의 list paragraph 스타일에서 들여쓰기 · 줄간격 · 정렬 · 폰트(rPr) 를 추출해 단락에 **direct formatting 으로** 강제 적용한다. pandoc 이 박는 자체 들여쓰기/폰트가 reference 의 디자인을 무시하는 문제를 막는다.

- 대상 단락 식별 기준: **`<w:pPr>` 안에 `<w:numPr>` 가 있는 모든 단락** — bullet (`-`, `*`, `+`) 과 ordered list (`1.`, `1)`) 둘 다 pandoc 이 numPr 로 만들기 때문에 자동으로 양쪽 다 커버된다. 단계 1.7 에서 promote 한 단락은 heading 이 되어 numPr 가 없으므로 영향받지 않는다.
- reference 에서 사용할 스타일 후보 (우선순위): `List Paragraph` → `ListParagraph` → `List Bullet` → `List Number`.
- 추출 항목: `<w:ind/>`, `<w:spacing/>`, `<w:jc/>` 그리고 `<w:rPr>...</w:rPr>` 전체 (있는 것만).
- 적용 규칙: 단락의 pPr 에 같은 태그가 있으면 reference 값으로 교체, 없으면 추가. rPr 도 동일 규칙으로 교체/추가.
- 로그: `[POSTPROCESS-LISTS]`
- 비활성화: `md2docx.py --no-postprocess` 로 통합 비활성 (단계 3·4 와 함께 꺼짐).
- 단독 호출도 가능:
  ```
  python postprocess_lists.py <docx> --reference <ref.docx>
  ```

### 단계 5.4: pandoc 출력 list_kind 스캔 (`userlist_scan_lists.py`)

`template/userlist-<label>.json` (cluster catalog) 이 존재하고 `<output_dir>/userlist-mapping.json` 이 아직 없으면, 변환 직후 pandoc 출력 docx 의 모든 numPr 단락을 `(numFmt, ilvl)` 단위로 묶어 dump 한다.

```
python userlist_scan_lists.py <output.docx> --out <scan.json>
```

- 출력 JSON: `{list_kinds: [{numFmt, ilvl, kind, count, sample_text, alt_samples, numIds}]}`.
- stdout: `[USERLIST-PANDOC-LIST] numFmt=<f> ilvl=<l> | kind=<unordered|ordered> | count=<n> | sample='<t>' | alt=[...] | numIds=[...]` + `[USERLIST-PANDOC-LIST-COUNT] kinds=<m>` + `[USERLIST-SCAN-OUT] <abs>`.
- returncode: list_kind 0건 = 0, 1건 이상 = 7.

returncode=7 시 md2docx.py 가 사용자 확인 배너 출력 후 `sys.exit(7)`. **Claude 의 처리 절차**:

1. catalog 의 cluster 정의들과 위 `[USERLIST-PANDOC-LIST]` list_kind 들을 함께 보여주며, 각 list_kind 마다 `AskUserQuestion` 으로 묻기:
   - 옵션: catalog 의 각 `cluster_id` (예: `userlist-□-firstLine440`) + `사용 안 함`
2. 답을 모아 `<output_dir>/userlist-mapping.json` 작성:

   ```json
   {
     "md": "report.md",
     "reference_label": "reg",
     "list_rules": [
       {"match": {"numFmt": "bullet", "ilvl": "0"}, "cluster_id": "userlist-□-firstLine440"},
       {"match": {"numFmt": "bullet", "ilvl": "1"}, "cluster_id": "userlist-◌-firstLine660"},
       {"match": {"numFmt": "decimal", "ilvl": "0"}, "cluster_id": null}
     ]
   }
   ```
3. 같은 명령으로 재실행 → mapping 발견 → 단계 5.4 스킵, 단계 5.5 후처리 진행.

### 단계 5.5: 사용자 정의 리스트 cluster 적용 (`postprocess_userlist.py`)

catalog + mapping 둘 다 존재하면, 변환 결과 docx 의 numPr 리스트 단락을 mapping 의 list_rule 에 따라 catalog 의 해당 cluster 패턴으로 재작성한다.

```
python postprocess_userlist.py <output.docx> --catalog <catalog.json> --mapping <mapping.json>
```

- 입력:
  - `--catalog`: `template/userlist-<label>.json` (per-reference cluster 정의)
  - `--mapping`: `<output_dir>/userlist-mapping.json` (per-conversion list_kind→cluster_id)
- 처리: 단락의 `(numFmt, ilvl)` 로 mapping 의 list_rule 조회 → cluster_id 로 catalog 의 cluster 조회 → numPr 제거, marker run prepend, indent/spacing/jc/rPr 적용. cluster_id=null 인 list_kind 는 그대로 둠 (pandoc 기본 유지).
- 로그: `[POSTPROCESS-USERLIST]`
- 비활성화:
  - `md2docx.py --no-userlist` → 단계 1.55/5.4/5.5 모두 비활성.
  - `md2docx.py --no-postprocess` → 표/페이지/리스트 후처리와 함께 비활성.
- 단독 호출:
  ```
  python postprocess_userlist.py <docx> --catalog template/userlist-<label>.json --mapping <output_dir>/userlist-mapping.json
  ```

`--skip-userlist` 는 단계 1.55/5.4 의 사용자 질문 단계만 건너뛰고, mapping 이 이미 있다면 본 단계 적용은 **유지** 된다.

### 단계 6: 검증 (`verify.py` — `--verify` 시)

매핑 적용/미적용 두 변환의:
- XML 레벨: `<w:pStyle>`, `<w:rStyle>`, `<w:tblStyle>` 참조가 styles.xml에 정의됐는지
- 페이지 레이아웃: `<w:pgSz>`, `<w:pgMar>`, `<w:cols>`, `<w:docGrid>` 가 reference 와 동일한지 (post-processing 효과 검증)
- PDF 추출: `docx2pdf`로 두 PDF 만들어 시각 비교 (Windows + MS Word 필요)

---

## 작동 흐름

```
[입력] <ref.docx> (필수) + <input.md> (선택) + --verify (선택)
   ↓
[자동 분기]
   ├─ docx만:           매핑만 수행 → template/<원본>_mapped.docx
   ├─ md만:             template/ 목록 출력, returncode=4 (사용자 선택 필요)
   ├─ md + --template:  template/ 의 mapped reference 로 변환 (매핑 스킵)
   ├─ md + docx:        매핑 + 변환 → template/<ref>_mapped.docx, <input>.docx
   └─ +--verify:        위 + 두 PDF 비교
   ↓
[출력] template/<ref>_mapped.docx + (옵션) <input>.docx + (옵션) verify_out/
```

---

## 자주 묻는 질문

**Q. 회사 reference에 코드 블록/링크 스타일이 없어요.**
→ `STUB_DEFINITIONS`이 합리적 디폴트(Consolas 폰트, 파란 링크 등)로 자동 생성. 회사 자체 스타일이 있으면 `map.py --map` JSON으로 지정. 결정 근거는 [`decisions.md`](./decisions.md).

**Q. 표 서식이 reference대로 안 나옵니다.**
→ Pandoc의 표 스타일 상속 사각지대. 셀 단위 direct formatting이 필요하면 toolkit의 `md2docx`(샘플 표 복제 방식, `c:\claude_toolkit\.claude\skills\md2docx\`).

**Q. 코드 블록 토큰 색이 안 나옵니다.**
→ `pandoc ... --highlight-style=tango` 옵션 추가. md2docx.py에서 옵션 전달이 필요하면 SKILL.md 확장 검토.

**Q. 헤딩이 "제 N 편/장" 같은 회사 번호로 안 나옵니다.**
→ 사용한 reference가 `_mapped.docx`인지 확인. 회사 reference의 `heading N` 스타일에 그 번호 매김이 정의돼 있는지 확인.

---

## 관련 파일

- [`md2docx.py`](./md2docx.py) — 통합 진입점 (인자 분기)
- [`map.py`](./map.py) — 매핑 분석·적용 엔진 (`--apply`, `--map`)
- [`lint.py`](./lint.py) — markdown 넘버링/heading 사전 검토 (외부 markdownlint 우선, 내장 fallback)
- [`strip.py`](./strip.py) — 패턴 카탈로그 기반 검출·치환 (사용자 확인 필요)
- [`references/strip_patterns.json`](./references/strip_patterns.json) — 누적 관리되는 정규식 패턴 카탈로그
- [`postprocess_tables.py`](./postprocess_tables.py) — pandoc 출력 docx 의 표 디자인 후처리 (tblLook + cnfStyle)
- [`postprocess_page.py`](./postprocess_page.py) — reference 의 페이지 여백(pgSz/pgMar/cols/docGrid) 을 모든 sectPr 에 동기화
- [`postprocess_lists.py`](./postprocess_lists.py) — bullet/머릿기호 단락(numPr) 에 reference 의 list paragraph ind/spacing/jc/rPr 강제 적용
- [`.env`](./.env) — 단계별 동작 토글 (`<단계>_APPLY_<속성>` 규약). 현재 `USERLIST_APPLY_RPR/INDENT/SPACING/JC`. 토글이 `false` 면 cluster 의 해당 속성 무시하고 단락 기존 값 유지 (예: `USERLIST_APPLY_RPR=false` → 폰트 본문 바탕글 유지)
- [`userlist_extract.py`](./userlist_extract.py) — reference 의 표준 스타일 단락 머릿글을 raw 로 cluster dedup 관찰 → `template/_userlist-<label>-observations.json` (단계 1.55, 마커 판정은 LLM 사후)
- [`userlist_scan_lists.py`](./userlist_scan_lists.py) — pandoc 출력 docx 의 numPr 리스트를 `(numFmt, ilvl)` 별로 dump → `<output_dir>/_userlist-pandoc-scan.json` (단계 5.4, list_kind 별 cluster 매핑 결정용)
- [`postprocess_userlist.py`](./postprocess_userlist.py) — `--catalog` + `--mapping` 둘을 함께 받아 변환 결과 docx 의 numPr 리스트를 cluster 패턴으로 재작성 (단계 5.5)
- [`template/userlist-<label>.json`](./template/) — per-reference cluster 카탈로그 (정의만). Claude 가 observations induction + 사용자 확인 후 Write
- `<output_dir>/userlist-mapping.json` — per-conversion list_kind→cluster_id 매핑. Claude 가 pandoc 스캔 결과 + catalog 보고 사용자 확인 후 Write. 다음 변환 시 `--reuse-userlist-mapping` / `--fresh-userlist-mapping` 으로 재사용/재분석 결정
- [`verify.py`](./verify.py) — 변환·XML·PDF 검증
- [`decisions.md`](./decisions.md) — 자동 매핑 결정 규칙 기록
- [`references/pandoc-docx-styles.md`](./references/pandoc-docx-styles.md) — Pandoc 인식 스타일 목록
- [`references/reference_reg.docx`](./references/reference_reg.docx) — 원본 회사 템플릿 (raw)
- [`template/`](./template/) — `_mapped.docx` (pandoc `--reference-doc` 카탈로그) 누적 보관 폴더. `--template <이름>` 으로 선택, 매핑 모드(`md2docx <ref.docx>`) 시 새 항목 추가됨
- [`template/reference_reg_mapped.docx`](./template/reference_reg_mapped.docx) — `reference_reg.docx` 매핑 결과
