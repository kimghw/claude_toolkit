---
name: md2docx_target
description: 사용자 target.docx (회사 양식 raw) → <target_stem>_template.docx (Pandoc 호환 reference, 외부 이름은 template) 변환만 수행하는 단일 기능 스킬. md→docx 변환(convert) 은 포함하지 않음. 회사 어휘(heading 1, Quote 등) 와 Pandoc 어휘(Heading 1, Block Text 등) 의 불일치를 SEMANTIC_HINTS / STUB_DEFINITIONS 기반 basedOn 상속으로 자동 해결해, <cwd>/md2docx_target/ 폴더에 <target_stem>_template.docx 와 <target_stem>_template.report.md 를 저장한다. 회사 numbering 은 markdown 리스트에 자동 적용하지 않으며(Pandoc 기본 유지) AskUserQuestion 게이트도 없다.
---

# md2docx_target — target.docx → template.docx (map only)

## 목적

**사용자 회사 양식 target.docx 하나를 받아 Pandoc 호환 reference(=template) docx 한 개를 생성한다.** 그게 전부다.

- 입력: target.docx (회사 양식 raw)
- 출력: `<cwd>/md2docx_target/<target_stem>_template.docx` (Pandoc `--reference-doc` 입력으로 쓸 수 있는 docx) + `<cwd>/md2docx_target/<target_stem>_template.report.md` (매핑 분석 리포트)
- **md → docx 변환은 본 스킬 범위 밖.** convert 가 필요하면 [`md2docx`](../md2docx/SKILL.md) 사용.

> **명명 메모**: 파일·폴더 외부 이름은 사용자 친숙도를 위해 **template** 으로 통일했지만, 기능적으로는 Pandoc 의 `--reference-doc` 입력 docx (canonical 용어 = reference) 이다. 본 스킬 코드 안에서는 `reference` 와 `template` 이 동일 객체를 가리킨다.

## 용어 (canonical, md2docx 와 동일)

| 용어 | 의미 |
|---|---|
| **target** | 회사가 가진 목표 스타일 원본 docx (회사 양식 raw). pandoc 이 직접 읽지 않는다 |
| **reference** | pandoc `--reference-doc` 가 받는 스타일 docx. target 을 매핑/정규화한 결과. **파일·폴더 외부 이름은 `template`** 으로 노출 (사용자 친숙도) — 본 스킬 안에서 reference = template 동일 객체 |
| **map** | target → reference 변환 단계. 본 스킬이 수행하는 유일한 작업 |

## 인자 형식

```
python map.py <target.docx>                           # 기본 — <cwd>/md2docx_target/ 에 저장
python map.py <target.docx> --out <path.docx>         # 출력 경로 명시
python map.py <target.docx> --map <mapping.json>      # 사용자 매핑 오버라이드
python map.py <target.docx> --report <path.md>        # 리포트 경로 명시
```

## 산출물

target 1개당 template docx + 리포트 1쌍이 생성된다:

| 산출물 | 경로 패턴 | 내용 |
|---|---|---|
| template docx | `<cwd>/md2docx_target/<target_stem>_template.docx` | target 의 styles.xml 에 Pandoc 어휘 스타일을 `basedOn` 으로 추가한 결과. Pandoc `--reference-doc` 입력으로 바로 사용 |
| 리포트 | `<cwd>/md2docx_target/<target_stem>_template.report.md` | 매핑 plan 분석 (exact / case_mismatch / semantic / stub / missing) + target 의 numbering.xml 참고용 덤프 |

stdout 신호 (rc=0 시) 와 에러 형식 상세는 §작동 흐름 의 "신호" 절 참조.

## 산출물 명명

**target 파일명 stem 뒤에 `_template` 접미사** (분리자는 언더스코어 `_`):

| target | template docx | report |
|---|---|---|
| `mydoc.docx` | `<cwd>/md2docx_target/mydoc_template.docx` | `<cwd>/md2docx_target/mydoc_template.report.md` |
| `회사양식.docx` | `<cwd>/md2docx_target/회사양식_template.docx` | `<cwd>/md2docx_target/회사양식_template.report.md` |
| `408_Statement.docx` | `<cwd>/md2docx_target/408_Statement_template.docx` | `<cwd>/md2docx_target/408_Statement_template.report.md` |

리포트는 template docx 의 stem 에 `.report.md` 를 붙인다 (`<target_stem>_template.report.md`). 같은 target 으로 재호출 시 덮어쓰기.

## 산출물 위치

기본은 **작업 루트(cwd) 의 `md2docx_target/`** 폴더 (cwd 하위 고정 단일 폴더). 폴더가 없으면 자동 생성. 같은 target 으로 재호출 시 그 폴더 안 1쌍을 덮어쓴다. 원본 target.docx 는 수정하지 않는다.

경로 오버라이드:
- `--out <path.docx>` — template docx 경로 명시 (cwd 기준 상대 경로 허용)
- `--report <path.md>` — 리포트 경로 명시 (기본은 `--out` 의 stem + `.report.md`)

---

## 사용 도구

| 도구 | 용도 |
|:---|:---|
| `Bash` | `python .claude/skills/md2docx_target/map.py <target.docx>` 실행 |
| `Read` | 산출물 `output/<stem>_ref.report.md` 검토 |

외부 의존성 없음 (Python 표준 라이브러리만 사용 — `zipfile`, `re`, `argparse`, `json`, `pathlib`).

---

## 호출 예시

```powershell
# 기본 — <cwd>/md2docx_target/ 에 template 저장
python .claude\skills\md2docx_target\map.py company.docx
# → <cwd>\md2docx_target\company_template.docx
# → <cwd>\md2docx_target\company_template.report.md

# 출력 경로 명시
python .claude\skills\md2docx_target\map.py company.docx --out company_template.docx

# 사용자 매핑 오버라이드 — 특정 Pandoc 이름을 target 의 특정 스타일에 강제 매핑
python .claude\skills\md2docx_target\map.py company.docx --map mapping.json
```

`mapping.json` 형식:

```json
{
  "paragraph": {
    "Block Text": "회사_인용_스타일_이름",
    "Source Code": "회사_코드_스타일_이름"
  },
  "character": {
    "Hyperlink": "회사_링크_스타일_이름"
  }
}
```

---

## 주입 대상 — Pandoc 스타일 카탈로그

본 스킬이 reference 에 추가(또는 매칭 확인)하는 Pandoc 스타일 전체 목록 (`map.py` 의 `PANDOC_STYLES` 상수). severity 는 누락 영향도 — `critical` 은 시각적으로 깨지고, `important` 는 일부 요소 무서식, `optional` 은 편의용.

### paragraph

| severity | Pandoc 이름 |
|---|---|
| critical | `Normal`, `Heading 1`, `Heading 2`, `Heading 3`, `Source Code` |
| important | `Title`, `Block Text`, **`Caption`**, `Heading 4`, `Heading 5`, `Heading 6` |
| optional | `Heading 7`~`Heading 9`, `Body Text`, `First Paragraph`, `Compact`, `Subtitle`, `Author`, `Date`, `Abstract`, `Abstract Title`, `Bibliography`, `Verbatim Code`, `Footnote Text`, **`Image Caption`**, **`Figure`**, **`Captioned Figure`**, `TOC Heading`, `toc 1`~`toc 9` |

### character

| severity | Pandoc 이름 |
|---|---|
| critical | `Verbatim Char`, `Hyperlink` |
| important | `Default Paragraph Font` |
| optional | `Footnote Reference` |

### table

| severity | Pandoc 이름 |
|---|---|
| critical | `Table` |

### 캡션 처리 (요약)

표·그림 캡션은 본 스킬이 항상 다루며, 다음 순서로 결정된다:

1. target 에 `Caption` w:name 이 정확히 있으면 → **exact** (추가 안 함)
2. `caption` (소문자 등) 만 있으면 → **case_mismatch** (Pandoc 이름의 새 스타일 추가, basedOn = 회사 스타일)
3. target 에 `Image Caption` / `Figure Caption` / `Table Caption` / `Caption Text` 가 있으면 → **semantic** (새 스타일 추가)
4. 모두 없으면 → **stub** 으로 "가운데 정렬 + 이탤릭 9pt + Normal basedOn" 스타일 자동 생성

`Image Caption` / `Figure` / `Captioned Figure` 도 동일한 우선순위로 별도 처리.

전체 매핑 후보·stub 디폴트값은 [`decisions.md`](./decisions.md) §3·§4, 코드는 `map.py` 의 `SEMANTIC_HINTS` / `STUB_DEFINITIONS`.

---

## 작동 원리

target.docx 의 styles.xml 을 분석해 Pandoc 이 기대하는 스타일 이름과 대응 관계를 결정한다. **target 의 기존 스타일은 그대로 두고**, 그것을 `basedOn` 으로 상속하는 새 스타일을 Pandoc 이름으로 추가한 docx 를 reference 로 저장한다.

```xml
<!-- target 원본 (그대로 유지) -->
<w:style w:styleId="1"><w:name w:val="heading 1"/>...</w:style>

<!-- reference 에 추가되는 새 스타일 -->
<w:style w:styleId="Heading1" w:customStyle="1">
  <w:name w:val="Heading 1"/>
  <w:basedOn w:val="1"/>
</w:style>
```

결과: 회사 서식이 그대로 보존되면서, Pandoc 이 output 에 박는 `<w:pStyle w:val="Heading1"/>` 참조가 이 새 스타일을 찾고 → `basedOn` 체인을 따라 회사 스타일이 적용된다.

### 매핑 우선순위 (`find_mapping`)

1. **user_override** — `--map` JSON 사용자 지정 (최우선)
2. **exact** — w:name 완전 일치 (이미 있음 — 추가 안 함)
3. **case_mismatch** — 대소문자만 다름 (예: `heading 1` ↔ `Heading 1`) → 새 스타일 추가
4. **semantic** — `SEMANTIC_HINTS` 기반 의미 매칭 (예: `Quote` → `Block Text`) → 새 스타일 추가
5. **stub** — 위 모두 실패하지만 `STUB_DEFINITIONS` 에 있음 → 합리적 디폴트로 새 스타일 생성
6. **missing** — 위 모두 실패 → skip (리포트에만 기록)

자동 매핑 결정 규칙 전문: [`decisions.md`](./decisions.md).

### Numbering 정책 — 게이트 없음 (조용히 진행)

target 의 `numbering.xml` 에 list 정의(예: `1.`, `①`, `가.`, `제 1)`)가 있어도 본 스킬은 **AskUserQuestion 을 호출하지 않는다.** 리포트의 "Numbering 정의" 섹션에 참고용으로만 표시하고 그대로 진행한다.

근거 (md2docx [`decisions.md`](../md2docx/decisions.md) 결정 8):
- target 의 numbering 정의는 거의 항상 heading 전용 (제 N 편/장/절)
- markdown 리스트와 heading 은 시각·의미적으로 별개 요소
- 회사 list 양식을 markdown 리스트에 적용하려면 `--map` 으로 `"paragraph": {"List Paragraph": "<w:name>"}` 명시 지정해 재실행

---

## 작동 흐름

```
[입력] <target.docx>
   ↓
map.py 호출
   ↓ (1) extract_styles — styles.xml 파싱
   ↓ (2) extract_numbering — numbering.xml 파싱 (리포트용)
   ↓ (3) compute_plan — PANDOC_STYLES × find_mapping
   ↓ (4) apply_mapping — case_mismatch + semantic + user_override + stub 새 스타일 XML 삽입
   ↓ (5) reference docx 저장 + report.md 저장
   ↓
[출력] output/<target_stem>_ref.docx
       output/<target_stem>_ref.report.md
```

신호:
- `[APPLY] N new styles added -> <path>` — 성공 (rc=0). N 은 추가된 새 스타일 수
- `[REPORT] <path>` — 리포트 경로
- 오류는 stderr 로 `ERROR: ...` 형식, rc=1

---

## md2docx 와의 관계

본 스킬은 [`md2docx`](../md2docx/SKILL.md) 의 **map 단계만** 떼어낸 단일 기능 도구다.

| 항목 | md2docx | md2docx_target (본 스킬) |
|---|---|---|
| 입력 | source.md (+ target.docx) | target.docx 만 |
| 출력 | output.docx + reference 등 | reference.docx 만 |
| 단계 | lint + strip + map + convert + postprocess + verify | **map 만** |
| AskUserQuestion | 5종 (template, lint, strip, numbering, ...) | **없음** |
| 명명 규약 | `reference-<label>.docx` (하이픈 접두사) | `<target_stem>_ref.docx` (`_ref` 접미사, stem 그대로) |
| 매핑 정책 | 공유 (동일한 SEMANTIC_HINTS / STUB_DEFINITIONS / decisions.md) | 공유 |

**언제 어떤 걸 쓰나:**
- 회사 양식 docx 하나만 받았고 reference 만 만들고 싶음 → **md2docx_target**
- 회사 양식 + 마크다운 원고가 있고 최종 docx 까지 만들고 싶음 → **md2docx**

---

## 관련 파일

- [`map.py`](./map.py) — map 분석·적용 엔진 (단일 진입점). target → reference + report 생성
- [`decisions.md`](./decisions.md) — 자동 매핑 결정 규칙
- [`output/`](./output/) — reference 산출물 누적 보관 폴더. 새 target 으로 호출할 때마다 항목 추가

## 자주 묻는 질문

**Q. md → docx 변환도 같이 해줄 수 있나요?**
→ 본 스킬 범위 밖입니다. 변환까지 필요하면 [`md2docx`](../md2docx/SKILL.md) 를 사용하세요.

**Q. target 에 코드 블록/링크 스타일이 없습니다.**
→ `STUB_DEFINITIONS` 가 합리적 디폴트(Consolas 폰트, 파란 링크 등)로 자동 생성합니다. 회사 자체 스타일이 있으면 `--map` JSON 으로 지정. 결정 근거는 [`decisions.md`](./decisions.md).

**Q. target 에 numbering 이 있는데 markdown 리스트에 적용하고 싶습니다.**
→ `mapping.json` 에 `"paragraph": {"List Paragraph": "회사_list_스타일_w:name"}` 추가 후 `--map mapping.json` 으로 재실행. 또는 output 을 Word 로 열어 List Paragraph 스타일의 numbering 을 회사 numId 로 수동 바인딩.
