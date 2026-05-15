# Pandoc이 인식하는 docx 스타일 전체 목록

Pandoc은 Markdown → DOCX 변환 시 reference.docx의 styles.xml에서 **스타일 이름**으로 매칭한다. 아래 이름과 정확히 일치하는 스타일이 reference.docx에 정의돼 있어야 해당 요소에 시각 속성이 적용된다.

이름이 일치하지 않으면 Word 기본값(`Normal`)으로 폴백된다.

---

## 단락 스타일 (Paragraph styles)

| 스타일 이름 | 적용 대상 |
|---|---|
| `Normal` | 기본 본문 |
| `Body Text` | 본문 텍스트 |
| `First Paragraph` | 첫 단락 |
| `Compact` | 좁은 단락 (리스트 항목 등) |
| `Title` | 문서 제목 (YAML `title`) |
| `Subtitle` | 부제 (YAML `subtitle`) |
| `Author` | 저자 (YAML `author`) |
| `Date` | 날짜 (YAML `date`) |
| `Abstract` | 초록 |
| `Abstract Title` | 초록 제목 |
| `Bibliography` | 참고문헌 |
| `Heading 1` ~ `Heading 9` | 제목 1~9단계 (`#` ~ `#########`) |
| `Block Text` | 인용 블록 (`> ...`) |
| `Source Code` | 코드 블록 (```` ``` ````) |
| `Verbatim Code` | verbatim 코드 |
| `Footnote Text` | 각주 본문 |
| `Caption` | 캡션 (그림/표 설명) |
| `Image Caption` | 이미지 캡션 |
| `Figure` | 그림 |
| `Captioned Figure` | 캡션 포함 그림 |
| `TOC Heading` | 목차 제목 |
| `toc 1` ~ `toc 9` | 목차 항목 |

---

## 문자 스타일 (Character styles)

| 스타일 이름 | 적용 대상 |
|---|---|
| `Default Paragraph Font` | 기본 문자 |
| `Verbatim Char` | 인라인 코드 (`` `code` ``) |
| `Hyperlink` | 링크 (`[text](url)`) |
| `Footnote Reference` | 각주 번호 |

---

## 표 스타일 (Table styles)

| 스타일 이름 | 적용 대상 |
|---|---|
| `Table` | 모든 표 (Pandoc은 `Table` 하나로만 매핑) |

> 표 인스턴스별 다른 서식이 필요하면 후처리(샘플 표 속성 복제)가 필요. toolkit의 `md2docx` 스킬 참고.

---

## 리스트 스타일

| 스타일 이름 | 적용 대상 |
|---|---|
| `List Paragraph` | 리스트 단락 |
| `Bullet List` | 글머리표 리스트 |
| `Numbered List` | 번호 리스트 |
| `Compact` | 리스트 내부 단락 (좁은 간격) |

---

## 코드 하이라이팅 (syntax highlighting)

코드 블록 내부 토큰의 색상은 `--highlight-style` 옵션이 처리한다 — **reference.docx에서 직접 손댈 필요 없음**.

토큰 스타일 이름 (참고용):

- `Keyword Tok` — 키워드 (`if`, `for`, ...)
- `DataType Tok` — 자료형
- `String Tok` — 문자열 리터럴
- `Comment Tok` — 주석
- `Function Tok` — 함수명
- `Variable Tok` — 변수명
- (외 약 20여 종)

사용 가능한 highlight-style 테마:

```
pygments, tango, espresso, zenburn, kate, monochrome, breezedark, haddock
```

확인:
```powershell
pandoc --list-highlight-styles
```

---

## 실용 우선순위 — 최소 7개부터 시작

전체를 다 손볼 필요는 없다. 보통 이 정도면 충분:

1. **`Normal`** — 본문 폰트/크기/줄간격 (전체에 영향)
2. **`Heading 1`** — 1단계 제목 (가장 큰 효과)
3. **`Heading 2`** — 2단계 제목
4. **`Heading 3`** — 3단계 제목
5. **`Source Code`** — 코드 블록 (고정폭 폰트, 배경색)
6. **`Verbatim Char`** — 인라인 코드 (고정폭 폰트, 강조)
7. **`Title`** — 문서 제목 (YAML metadata 사용 시)

추가로 자주 쓰는 것:

8. **`Table`** — 표 테두리/정렬/줄 색상
9. **`Caption`** — 그림/표 캡션
10. **`Block Text`** — 인용구
11. **`Hyperlink`** — 링크 색상/밑줄

---

## reference.docx 생성·편집 절차

### 1. 기본 템플릿 추출

```powershell
pandoc -o reference.docx --print-default-data-file reference.docx
```

### 2. Word로 열기

추출된 `reference.docx`를 Word로 연다. 글자 내용은 무시한다 — **스타일 정의만** 수정한다.

### 3. 스타일 창에서 편집

홈 탭 → 스타일 창 우하단 화살표 → 전체 스타일 목록 표시.

수정할 스타일을 우클릭 → "수정" → 폰트, 크기, 색상, 정렬, 간격 등 조정.

### 4. 저장

저장 후 `pandoc ... --reference-doc=reference.docx`로 변환에 사용.

---

## 디버깅

**Q. 스타일이 적용 안 된다.**

- reference.docx에 해당 스타일 이름이 정확히 존재하는지 확인 (대소문자, 공백 포함)
- 변환 후 docx를 ZIP으로 풀어 `word/styles.xml`에서 `<w:style w:styleId="..." w:name="Heading 1">` 확인

**Q. 표 가운데 정렬이 풀린다.**

- Pandoc의 표 스타일 상속 사각지대 (고아 `pStyle`, 기본 `tblLook`). 셀 단위 direct formatting 필요.
- toolkit의 `md2docx` 스킬 사용: `c:\claude_toolkit\.claude\skills\md2docx\`

**Q. 한글 폰트가 깨진다.**

- reference.docx의 `Normal` 스타일에서 **본문 폰트**와 **아시아 텍스트 폰트** 모두 한글 폰트(맑은 고딕, 나눔고딕 등)로 지정.

---

## 참고 자료

- Pandoc 공식 문서: https://pandoc.org/MANUAL.html#option--reference-doc
- Pandoc docx 스타일 매핑 소스: https://github.com/jgm/pandoc/blob/main/src/Text/Pandoc/Writers/Docx.hs
