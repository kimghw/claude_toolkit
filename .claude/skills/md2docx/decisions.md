# 매핑 결정 기록 (decisions log)

이 문서는 `md2doc_style_matching` 스킬이 reference.docx를 처리할 때 적용하는 **모든 자동 결정 규칙**을 기록한다. 새로운 reference.docx가 입력되어도 동일한 규칙으로 처리된다.

모든 결정은 `map.py`의 데이터 상수로 인코딩되어 있다.

---

## 결정 1: Pandoc 스타일 분류 — `PANDOC_STYLES` (map.py)

Pandoc이 출력 docx에 참조하는 스타일을 **severity**로 분류:

- **critical**: 누락 시 변환 결과가 시각적으로 깨짐 (`Normal`, `Heading 1-3`, `Source Code`, `Verbatim Char`, `Hyperlink`, `Table`)
- **important**: 누락 시 일부 요소 무서식 (`Title`, `Block Text`, `Caption`, `Heading 4-6`)
- **optional**: 편의 스타일 (`Heading 7-9`, `Body Text`, `toc 1-9`, 등)

severity에 따라 리포트 강조와 stub 생성 우선순위가 달라진다.

---

## 결정 2: 매칭 우선순위 — `find_mapping` (map.py)

각 Pandoc 기대 스타일에 대해 회사 템플릿을 다음 순서로 매칭:

1. **user_override** — `--map` JSON 사용자 지정 (최우선)
2. **exact** — w:name 완전 일치 (이미 있음 — 아무것도 안 함)
3. **case_mismatch** — 대소문자만 다름 (예: `heading 1` ↔ `Heading 1`) → 새 스타일 추가
4. **semantic** — `SEMANTIC_HINTS` 기반 의미 매칭 → 새 스타일 추가
5. **stub** — 위 모두 실패하지만 `STUB_DEFINITIONS`에 있음 → 디폴트 stub 생성
6. **missing** — 위 모두 실패 → skip

---

## 결정 3: 의미 매핑 규칙 — `SEMANTIC_HINTS` (map.py)

회사 템플릿에 자주 등장하는 이름 패턴 ↔ Pandoc 어휘 매핑:

| Pandoc 이름 | 매칭 후보 (회사 템플릿) |
|---|---|
| `Block Text` | `Quote`, `Intense Quote`, `Blockquote`, `인용` |
| `Source Code` | `Code`, `Code Block`, `Preformatted Text`, `HTML Preformatted` |
| `Caption` | `Image Caption`, `Figure Caption`, `Table Caption`, `Caption Text` |
| `Table` | `Table Grid`, `Normal Table`, `Plain Table 1`, `Grid Table` |
| `Verbatim Char` | `Code Char`, `Inline Code`, `Code`, `Source Code Char` |
| `Hyperlink` | `Hyperlink`, `Internet Link`, `Link` |
| `Footnote Reference` | `Footnote Reference`, `Footnote Anchor` |
| `Body Text` | `Body Text`, `Body Text 1`, `본문` |
| `First Paragraph` | `First Paragraph`, `First Line` |
| `Compact` | `List Paragraph`, `Compact` |
| `toc 1~9` | `toc N`, `TOC N`, `heading N`, `Heading N` |
| 기타 | (map.py SEMANTIC_HINTS 참조) |

**근거**: Word 빌트인 스타일명, MS Office 영문/한글 로컬라이즈, 일반적 회사 템플릿 관례에서 추출.

매칭 성공 시 새 스타일을 `basedOn` 상속으로 추가:
- styleId: Pandoc 이름의 alphanumeric 압축 (예: `Block Text` → `BlockText`)
- w:name: Pandoc 이름 그대로
- basedOn: 회사 템플릿의 매칭된 스타일 styleId
- w:customStyle="1" 표시

---

## 결정 4: Stub 디폴트 — `STUB_DEFINITIONS` (map.py)

`semantic` 매칭이 실패하는 Critical/중요 스타일에 대해 합리적 디폴트로 새 스타일 생성:

| 스타일 | type | 디폴트 | basedOn | 근거 |
|---|---|---|---|---|
| `Verbatim Char` | character | Consolas + 회색 배경(#F2F2F2) | (없음) | 인라인 코드 관례 — Word 기본 Inline Code 스타일과 동일 |
| `Hyperlink` | character | 파란색(#0563C1) + 밑줄 | (없음) | Word 기본 Hyperlink 스타일과 동일 |
| `Source Code` | paragraph | Consolas 10pt + 좌측 들여쓰기 + 간격 | Normal | 코드 블록 관례 — 회사 본문 폰트와 분리 |
| `Caption` | paragraph | 가운데 정렬 + 이탤릭 9pt | Normal | Word 기본 Caption 스타일과 유사 |
| `Footnote Text` | paragraph | 9pt | Normal | Word 기본 각주 본문과 동일 |
| `Footnote Reference` | character | 윗첨자 | (없음) | Word 기본 각주 참조와 동일 |
| `Image Caption` | paragraph | Caption과 동일 (가운데 + 이탤릭 9pt) | Normal | 이미지 캡션은 일반 캡션 변형 |
| `TOC Heading` | paragraph | 굵게 16pt + 위 간격 | Heading 1 | 목차 제목은 헤딩 변형 |

**디폴트 설계 원칙**:
- 회사 양식의 본문(Normal)과 시각적으로 명확히 구분되되, 회사 양식을 해치지 않음
- Word 빌트인 스타일과 색상/폰트 일치 (`Hyperlink` 파란색, `Verbatim Char` 회색 배경 등)
- paragraph stub은 가능한 한 회사 `Normal`을 `basedOn`으로 상속 → 회사 폰트 패밀리 유지

---

## 결정 5: 매핑 안 함 — 정책적 제외

회사 템플릿에 있어도 의도적으로 매핑하지 않는 경우:

| 회사 스타일 | 제외 이유 |
|---|---|
| `Intense Quote` | `Quote`가 이미 `Block Text`에 매핑됨. Pandoc은 'intense' 인용 개념 없음 |
| `Intense Emphasis`, `Intense Reference` | Pandoc은 markdown `**bold**`/`*italic*`을 character 스타일이 아닌 direct formatting으로 처리 |
| `header`, `footer` | Pandoc은 머리글/바닥글을 `sectPr`로 처리, 스타일 매핑과 무관 |
| `Plain Table 1`, `Normal Table` | `Table Grid`가 이미 `Table`에 매핑됨 |
| 헤딩 character 스타일 (`제목 N Char` 등) | Pandoc은 character 변형 사용 안 함 |

이 결정은 코드 레벨에서 강제되지 않음 (단순히 SEMANTIC_HINTS에 없을 뿐). 필요 시 `--map`으로 강제 매핑 가능.

---

## 결정 6: Pandoc 자체 처리 위임

다음 스타일은 회사 템플릿/매핑 처리 대상이 아님 — Pandoc이 출력 docx에 직접 정의를 삽입:

- 코드 하이라이팅 토큰 (`KeywordTok`, `StringTok`, `BuiltInTok`, `NormalTok` 등 약 20여 종)
  - `--highlight-style` 옵션이 처리
- `SourceCode` (paragraph)도 Pandoc이 일부 버전에서 자동 추가 — 하지만 안정성을 위해 STUB_DEFINITIONS에 포함

---

## 결정 7: 변환 후 검증 정책

매핑 적용 후 동작 검증:
1. **XML 레벨**: `test.md` → 변환 → document.xml의 모든 `<w:pStyle>`, `<w:rStyle>`, `<w:tblStyle>` 참조가 styles.xml에 정의돼 있는지 확인 (자동화 가능)
2. **시각 레벨**: Word/LibreOffice/PDF 변환 후 회사 양식 적용 여부 확인 (수동)

판단이 모호하면 PDF 출력 후 비교 (사용자 지시).

---

## 다음 reference.docx 들어왔을 때의 처리 흐름

```
[입력] 새 reference.docx
   ↓
map.py 호출
   ↓ (1) extract_styles: styles.xml 파싱
   ↓ (2) compute_plan: PANDOC_STYLES × find_mapping
   ↓        → user_override / exact / case_mismatch / semantic / stub / missing 분류
   ↓ (3) apply_mapping: case_mismatch + semantic + user_override + stub 모두 새 스타일 추가
   ↓ (4) 출력 docx: 회사 스타일 그대로 + Pandoc 어휘 매핑 추가
   ↓
[출력] reference_mapped.docx
```

이 흐름은 reference.docx 종류와 무관하게 동일하게 적용된다. 새 결정 규칙이 필요하면 `SEMANTIC_HINTS` 또는 `STUB_DEFINITIONS`에 추가하고 본 문서에 기록.

---

## 결정 8: Markdown 리스트 numbering 정책

회사 reference에 list 전용 numbering 정의가 없는 일반적 경우, markdown 일반 리스트(`1.`, `2.`, `-`, `*`)는 **Pandoc 기본 양식 그대로** 사용.

**근거**:
- 회사 reference의 numbering 정의는 거의 항상 heading 전용 (제 N 편/장/절, 1./1.1./1.1.1. 등)
- markdown 리스트와 heading은 시각·의미적으로 별개 요소
- list 전용 회사 양식이 있는 경우만 예외적으로 mapping.json으로 명시 매핑

**기본 동작**: `map.py`가 numbering 정의 발견 시 `[NUMBERING]` 신호 출력, `md2docx.py`가 stdout으로 알림. SKILL.md에 따라 Claude가 사용자에게 `AskUserQuestion`으로 확인. **기본 권장 응답은 "Pandoc 기본 유지"** (사용자 결정 2026-05-15).

**예외 적용 시 (사용자가 회사 list 양식을 원할 때)**:
- `mapping.json`에 `"paragraph": {"List Paragraph": "회사_list_스타일_w:name"}` 추가 후 `map.py --map mapping.json` 재실행
- 또는 출력 docx를 Word로 열어 List Paragraph 스타일의 numbering을 회사 numId로 수동 바인딩

---

## 변경 이력

- 2026-05-15 — 초기 작성. SEMANTIC_HINTS와 STUB_DEFINITIONS 기반 자동 매핑 정책 수립.
- 2026-05-15 — 결정 8 추가. Numbering 정책 — 사용자 확인 결과 "Pandoc 기본 유지"가 기본값.
