---
name: md2docx
description: Markdown(.md)을 회사 양식의 Word(.docx)로 변환. 단일 진입점 md2docx.py가 인자(파일 확장자)로 자동 분기 — docx만 주면 매핑만 수행해 template/<원본>_mapped.docx 로 저장, md+docx 주면 매핑 후 변환, md 만 주면 template/ 목록 출력 후 사용자 선택. --verify로 XML/PDF 검증. 회사 reference와 Pandoc 어휘 불일치(heading 1 vs Heading 1, Quote vs Block Text 등)는 SEMANTIC_HINTS/STUB_DEFINITIONS로 자동 매핑.
---

# md2docx — Markdown → DOCX 통합 파이프라인

## 인자 형식

단일 진입점 `md2docx.py`가 파일 확장자로 자동 분기:

| 호출 | 동작 |
|---|---|
| `md2docx help` (또는 `-h`, `--help`, 인자 없음) | 사용법 출력 |
| `md2docx <ref.docx>` | **매핑만** — `template/<원본>_mapped.docx` 생성 |
| `md2docx <input.md>` | **template 선택 요청** — template/ 목록 출력, returncode=4. Claude 가 AskUserQuestion 으로 사용자에게 묻고 `--template <이름>` 으로 재실행 |
| `md2docx <input.md> --template <이름>` | **template/ 에서 선택 후 변환** — 매핑 단계 스킵 |
| `md2docx <input.md> <ref.docx>` | **매핑 + 변환** — `template/<ref>_mapped.docx` 생성 후 변환 |
| `md2docx <input.md> <ref.docx> --verify` | 위 + XML/PDF 검증 |

### 산출물 위치 규칙

**mapped reference 는 항상 skill 의 `template/` 폴더에 누적**된다 (재사용 가능한 pandoc reference 카탈로그). 이 덕분에 한 번 매핑한 회사 reference 는 이후 `--template <이름>` 한 줄로 재사용 가능.

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

**현재 카탈로그**

| id | kind | 정규식 → 치환 | 효과 (reference_reg 기준) |
|---|---|---|---|
| `heading-manual-number` | remove | `^(#+\s+)\d+(?:\.\d+)*\.?\s+` → `\1` | `## 1. 핵심` → `## 핵심` (회사 h2 자동 번호 `제 1 장` 만 남김) |
| `promote-top-bullets-to-h6` | promote | `^(- \|\* \|\+ )` → `###### ` | `- 항목` → `###### 항목` (h6 `(1)(2)(3)` 자동 번호) |
| `promote-top-ordered-to-h5` | promote | `^(\d+)[.)]\s+` → `##### ` | `1. 단계` → `##### 단계` (h5 `1.2.3.` 자동 번호) |
| `remove-hrule` | remove | `^[ \t]*(?:-{3,}\|\*{3,}\|_{3,})[ \t]*\r?\n?` → '' | `---`, `***`, `___` 같은 horizontal rule 줄 통째 제거 (회사 양식은 heading 자동 번호로 구분) |

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

`--no-postprocess` 로 끌 수 있다 (단계 4 페이지 레이아웃 동기화도 함께 비활성됨 — 두 단계 모두에 적용).

### 단계 4: 페이지 레이아웃 동기화 (`postprocess_page.py`)

reference 의 마지막 `<w:sectPr>` 에서 `<w:pgSz>`, `<w:pgMar>`, `<w:cols>`, `<w:docGrid>` 를 추출해 변환 결과 docx 의 **모든 sectPr 에 덮어쓴다**. pandoc 의 `--reference-doc` 가 보통 sectPr 를 복사하지만, 별도 sectPr 가 끼어들거나 reference 가 교체되어도 회사 양식의 페이지 여백·용지 크기·단·격자 설정이 보장된다.

- 로그: `[POSTPROCESS-PAGE]`
- 비활성화: `md2docx.py --no-postprocess` 로 통합 비활성 (단계 3 표 디자인과 함께 꺼짐). 별도 `--no-page-sync` 같은 md2docx.py 인자는 없음.
- 단독 호출도 가능:
  ```
  python postprocess_page.py <docx> --reference <ref.docx>
  ```

### 단계 5: 검증 (`verify.py` — `--verify` 시)

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
- [`verify.py`](./verify.py) — 변환·XML·PDF 검증
- [`decisions.md`](./decisions.md) — 자동 매핑 결정 규칙 기록
- [`references/pandoc-docx-styles.md`](./references/pandoc-docx-styles.md) — Pandoc 인식 스타일 목록
- [`references/reference_reg.docx`](./references/reference_reg.docx) — 원본 회사 템플릿 (raw)
- [`template/`](./template/) — `_mapped.docx` (pandoc `--reference-doc` 카탈로그) 누적 보관 폴더. `--template <이름>` 으로 선택, 매핑 모드(`md2docx <ref.docx>`) 시 새 항목 추가됨
- [`template/reference_reg_mapped.docx`](./template/reference_reg_mapped.docx) — `reference_reg.docx` 매핑 결과
