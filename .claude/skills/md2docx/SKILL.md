---
name: md2docx
description: Markdown(.md)을 회사 양식의 Word(.docx)로 변환. 단일 진입점 md2docx.py가 인자(파일 확장자)로 자동 분기 — docx만 주면 매핑만 수행해 <원본>_mapped.docx 저장, md+docx 주면 매핑 후 회사 양식으로 변환. --verify로 XML/PDF 검증. 회사 reference와 Pandoc 어휘 불일치(heading 1 vs Heading 1, Quote vs Block Text 등)는 SEMANTIC_HINTS/STUB_DEFINITIONS로 자동 매핑.
---

# md2docx — Markdown → DOCX 통합 파이프라인

## 인자 형식

단일 진입점 `md2docx.py`가 파일 확장자로 자동 분기:

| 호출 | 동작 |
|---|---|
| `md2docx help` (또는 `-h`, `--help`, 인자 없음) | 사용법 출력 |
| `md2docx <ref.docx>` | **매핑만** — `<원본>_mapped.docx` 생성 |
| `md2docx <input.md> <ref.docx>` | **매핑 + 변환** — `<input>.docx` 생성 |
| `md2docx <input.md> <ref.docx> --verify` | 위 + XML/PDF 검증 |

옵션:

| 플래그 | 설명 |
|---|---|
| `--verify` | verify.py 호출해 XML + PDF 비교 |
| `--out <file>` | 변환 결과 경로 덮어쓰기 |

`<ref.docx>` 이름이 이미 `_mapped`로 끝나면 매핑 단계 자동 생략.

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

# 새 회사 양식 받았을 때 — 매핑만
python .claude\skills\md2docx\md2docx.py company.docx
# → company_mapped.docx 생성

# 일상 변환 — md를 회사 양식 docx로
python .claude\skills\md2docx\md2docx.py report.md company.docx
# → report.docx 생성 (회사 양식 적용)

# 변환 + 시각 검증
python .claude\skills\md2docx\md2docx.py report.md company.docx --verify

# 매핑된 파일 직접 지정 (1회 매핑 후 반복 변환에 효율적)
python .claude\skills\md2docx\md2docx.py report.md company_mapped.docx
# → 매핑 단계 자동 스킵, 변환만 수행
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

### 단계 2: 변환 (pandoc 호출)

```
pandoc <input.md> -o <output.docx> --reference-doc=<mapped.docx>
```

### 단계 3: 검증 (`verify.py` — `--verify` 시)

매핑 적용/미적용 두 변환의:
- XML 레벨: `<w:pStyle>`, `<w:rStyle>`, `<w:tblStyle>` 참조가 styles.xml에 정의됐는지
- PDF 추출: `docx2pdf`로 두 PDF 만들어 시각 비교 (Windows + MS Word 필요)

---

## 작동 흐름

```
[입력] <ref.docx> (필수) + <input.md> (선택) + --verify (선택)
   ↓
[자동 분기]
   ├─ docx만:   매핑만 수행 → <원본>_mapped.docx
   ├─ md+docx:  매핑 + 변환 → <input>.docx
   └─ +--verify: 위 + 두 PDF 비교
   ↓
[출력] _mapped.docx (Pandoc reference) + (옵션) 변환 docx + (옵션) verify_out/
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
- [`verify.py`](./verify.py) — 변환·XML·PDF 검증
- [`decisions.md`](./decisions.md) — 자동 매핑 결정 규칙 기록
- [`references/pandoc-docx-styles.md`](./references/pandoc-docx-styles.md) — Pandoc 인식 스타일 목록
- [`references/reference_reg.docx`](./references/reference_reg.docx) — 원본 회사 템플릿
- [`references/reference_reg_mapped.docx`](./references/reference_reg_mapped.docx) — 매핑 적용된 reference
