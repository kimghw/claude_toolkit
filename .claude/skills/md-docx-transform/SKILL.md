---
name: md-docx-transform
description: Markdown(.md) 파일을 Pandoc + 사전 준비된 Word 템플릿(.docx 또는 .dotx)으로 DOCX로 변환하고, 템플릿의 샘플 표 서식을 출력 표에 평탄화 주입해 스타일 상속 손실을 제거한다. 미정의 style 참조를 리포트한다. **호출 시 먼저 `extract-docx-styles`로 템플릿을 정비한 뒤 변환을 실행한다.**
---

# md-docx-transform — Markdown → DOCX 변환·복제 가이드

Word 템플릿으로 `.md` 파일을 `.docx`로 변환하고, **템플릿의 샘플 표 서식을 출력 표에 강제 주입**해 Pandoc이 만들어내는 스타일 상속 사각지대(고아 `pStyle`, 기본 `tblLook` 등)를 피한다.

---

## 입력

| 파라미터 | 설명 | 형식 |
|---|---|---|
| `--md` | 변환할 Markdown 파일 | `.md` |
| `--ref` | Word 템플릿 | `.docx` 또는 `.dotx` (자동 처리) |
| `--out` | 출력 파일 경로 | `.docx` |

`.dotx`는 자동으로 임시 `.docx`로 복사되어 Pandoc에 전달된다. 원본 `.dotx`는 변경되지 않는다.

---

## 호출 절차 (중요)

### Step 0 — `extract-docx-styles` 선행 실행

먼저 `extract-docx-styles` 스킬을 템플릿에 대해 실행해 스타일이 정비되어 있는지 확인한다:

- Pandoc 필수 `w:name`(`Normal`, `heading 1~6`, `Table`) 존재 여부
- `Table` 스타일 존재 (없으면 기존 `w:type="table"` 스타일을 `basedOn`으로 상속해 추가)
- 여러 표 스타일이 있으면 사용자에게 기본값 확인

### Step 1~ — `transform.py` 실행

아래 "작업 절차" 섹션대로 진행.

---

## 전제

- Pandoc 설치 완료 (`pandoc --version` 확인)
- Python 3.8+ (표준 라이브러리만 사용)
- 템플릿이 `.docx` 또는 `.dotx` 형식이며 **최소 하나 이상의 표(샘플)** 를 포함

---

## 핵심 원리 — 왜 "복제"인가

### 기존 문제: 스타일 상속은 5단 계층, 어느 한 단에서 가려짐

Pandoc은 표 셀 문단마다 `<w:pStyle w:val="Compact"/>`를 기록한다. 템플릿에 `Compact` 정의가 없으면 Word는 `Normal`로 폴백하고, 그 때의 `jc` 기본값(left)이 **표 스타일의 `jc=center`보다 우선**한다. 결과: 템플릿에는 가운데 정렬로 정의돼 있는데 출력은 왼쪽 정렬.

### 해결: 샘플 표 속성을 평탄화해 direct formatting으로 주입

1. 템플릿의 **샘플 표**(첫 번째 또는 `--sample-index N`으로 지정)에서 `<w:tblPr>`, `<w:tblGrid>` 추출
2. 샘플이 참조하는 `<w:tblStyle>` 체인을 styles.xml에서 **평탄화**
   - 기본 `<w:pPr>`/`<w:tcPr>`/`<w:trPr>`/`<w:tblPr>`
   - 조건부 `<w:tblStylePr w:type="firstRow|firstCol|lastRow|...">` 각각의 블록
3. 출력 표의 각 셀(row i, col j)에 대해 **OOXML 우선순위** 대로 조건부 서식을 overlay:

   `wholeTable → band1/2 Horz → band1/2 Vert → firstCol → lastCol → firstRow → lastRow → corner cells`

   - **줄무늬(banded)**: `band1Horz`/`band2Horz`/`band1Vert`/`band2Vert` 블록이 실제로 적용된다. 적용 조건은 ① 스타일 체인에 해당 블록이 존재하고, ② 샘플 표(또는 스타일)의 `<w:tblLook>`에서 `noHBand`/`noVBand`가 해제되어 있을 때. 밴드 크기는 스타일의 `<w:tblStyleRowBandSize>`/`<w:tblStyleColBandSize>`(기본 1)를 따르며, `firstRow`/`lastRow`/`firstCol`/`lastCol` 블록이 정의된 경우 해당 행·열은 body 범위에서 제외된다.

4. 그 결과 effective pPr/tcPr을 셀에 **direct formatting** 으로 주입
5. Markdown 명시 alignment(`|:---:|`, `|---:|`)는 기본 **보존** — `--override-jc`로 덮어쓰기 가능

→ 스타일 상속을 거치지 않으므로 고아 `pStyle`·pandoc `tblLook` 무관하게 동작.

---

## 작업 절차

### 1. 변환·복제 통합 실행 (권장)

[`transform.py`](./transform.py)가 Pandoc 변환 → 샘플 복제 → 고아 참조 리포트를 한 번에 수행한다:

```bash
python .claude/skills/md-docx-transform/transform.py \
  --md input.md \
  --ref references/templates/your-template.docx \
  --out output.docx
```

Windows PowerShell:

```powershell
python .claude\skills\md-docx-transform\transform.py `
  --md input.md `
  --ref references\templates\your-template.docx `
  --out output.docx
```

출력 예:

```
[0/3] Template preflight (Pandoc readiness check)...
        OK — template has required Pandoc style names.
[1/3] Pandoc conversion...
        cmd: pandoc input.md --reference-doc=... -o output.docx
        OK (output.docx, 18111 bytes)
[2/3] Apply template table formatting to output...
        template tables: 1
          [0] 4r x 5c  style='aa'  width=0 auto  tblLook=firstRow,firstColumn  borders=Y
          → using sample index 0
          style chain: aa -> a1
          conditional regions: ['firstCol', 'firstRow']
        target tables: 3
        applied: 12 rows, 40 cells (markdown alignment preserved)
        → cloned sample[0] (style chain: aa->a1) onto 3 output table(s); 12 rows, 40 cells.
[3/3] Orphan style reference check...
        Orphan style references (missing in template's styles.xml):
          pStyle   BlockText, BodyText, Compact, FirstParagraph
          rStyle   Hyperlink, VerbatimChar
        -> Consider re-running extract-docx-styles to add these.
```

### 2. 옵션

| 플래그 | 기본 | 설명 |
|---|---|---|
| `--sample-index N` | `0` | 템플릿에 표가 여러 개일 때 어느 것을 샘플로 쓸지 지정. 생략하면 첫 번째 표를 쓰고, 여러 개 있으면 목록이 출력돼 재실행할 수 있다 |
| `--override-jc` | off | markdown `:---:`/`---:` 정렬을 무시하고 샘플 스타일의 `jc`로 전부 덮어씀 |
| `--center-tables` | off | 출력 표들의 `<w:tblPr>`에 `<w:jc w:val="center"/>`를 주입해 페이지 기준 가운데 정렬 (셀 텍스트 정렬과 독립) |
| `--no-clone-table` | off | 복제 단계 건너뛰고 레거시 `tblLook` 플래그만 보정 (템플릿에 샘플 표가 없거나 직접 formatting을 원할 때) |
| `--dry-run` | off | 변환만 하고 복제·보정 생략 |
| `--skip-preflight` | off | 템플릿 검증 건너뛰기 (`extract-docx-styles`가 이미 돈 경우) |
| `--verbose` | off | 표별 행/셀 수, 조건부 영역 등 상세 출력 |

### 3. 독립 실행 — 복제만 따로 (옵션)

이미 생성된 docx에 복제만 돌리고 싶으면 [`clone_table_props.py`](./clone_table_props.py)를 직접 호출:

```bash
python .claude/skills/md-docx-transform/clone_table_props.py \
  --template references/templates/your-template.docx \
  --target output.docx
```

샘플 표 목록만 확인:

```bash
python .claude/skills/md-docx-transform/clone_table_props.py \
  --template references/templates/your-template.docx \
  --target output.docx \
  --list-only
```

---

## 통합 워크플로우

```
[입력] 사용자 Word 템플릿 (.docx/.dotx) + input.md
         ↓
[/md-docx-transform 호출]
         ├─ Step 0: extract-docx-styles 선행 실행 (템플릿 검증·정비)
         ├─ Step 1: .dotx면 임시 .docx로 복사, Pandoc 변환
         ├─ Step 2: 템플릿 샘플 표 속성 추출·평탄화 → 출력 표에 direct formatting으로 주입
         └─ Step 3: 고아 style 참조 리포트 (자동 보정 안 함)
         ↓
    최종 output.docx
```

- 템플릿에 **샘플 표가 여러 개**면 `[2/3]` 단계에서 목록이 출력되고 기본 index 0으로 진행 — 다른 것을 쓰려면 `--sample-index N`으로 재실행.
- `extract-docx-styles`는 한 번 정비해두면 재실행 시 빠르게 통과(검증만).

---

## 제한 사항

- **샘플 표가 없으면 복제 불가.** 템플릿에 최소 하나의 `<w:tbl>`이 있어야 한다. 없으면 `--no-clone-table` 동작과 동일하게 레거시 `tblLook` 보정으로 폴백.
- **미정의 style 참조는 리포트만.** 템플릿 수정은 `extract-docx-styles`의 책임.
- **표 인스턴스별 개별 서식 불가**: 모든 출력 표가 동일 샘플 속성을 받는다. 표마다 다른 서식을 원하면 Word에서 수동 편집.
- **Pandoc 버전별 출력 차이**: 일부 버전은 `tblLook`을 `<w:tblLook w:val="0420">` 비트필드로만 기록 — 레거시 경로는 속성·비트필드 둘 다 처리.
- **상속 사이클**: 스타일 basedOn 체인에 사이클이 있으면 경고만 내고 중단.

---

## 관련 스킬·파일

- [`extract-docx-styles`](../extract-docx-styles/SKILL.md) — 템플릿 스타일 정비 (선행)
- [`transform.py`](./transform.py) — 통합 파이프라인 (CLI)
- [`clone_table_props.py`](./clone_table_props.py) — 샘플 표 속성 복제 엔진 (독립 실행 가능, transform.py가 내부 호출)
