# Style Mapping Plan

- **Input**: `c:\Users\USER\md2doc\.claude\skills\md2docx\references\reference_reg.docx`
- **Output**: `C:\Users\USER\md2doc\.claude\skills\md2docx\template\reference-reg.docx`
- **Template styles**: 39
- **Numbering 정의**: 12개 발견 (markdown 리스트 적용 여부는 사용자 확인 필요)

## 회사 reference의 Numbering 정의 — 사용자 확인 필요

Markdown의 numbered list (`1.`, `2.`) 또는 bullet list (`-`, `*`)가 
아래 회사 양식 numbering 중 하나를 사용해야 한다면, **사용자에게 적용 여부를** 확인하세요.

| abstractNumId | 레벨 | numFmt | 표시 텍스트 |
|---|---|---|---|
| 0 | 0 | decimal | `%1.` |
| 0 | 1 | upperLetter | `%2.` |
| 0 | 2 | lowerRoman | `%3.` |
| 1 | 0 | decimal | `제 %1 편` |
| 1 | 1 | decimal | `제 %2 장` |
| 1 | 2 | decimal | `제 %3 절` |
| 2 | 0 | bullet | `□` |
| 2 | 1 | bullet | `` |
| 2 | 2 | bullet | `` |
| 3 | 0 | bullet | `` |
| 3 | 1 | bullet | `` |
| 3 | 2 | bullet | `` |
| 4 | 0 | decimal | `%1` |
| 4 | 1 | decimal | `%1.%2` |
| 4 | 2 | decimal | `%1.%2.%3` |
| 5 | 0 | decimal | `%1.` |
| 5 | 1 | upperLetter | `%2.` |
| 5 | 2 | lowerRoman | `%3.` |
| 6 | 0 | decimal | `%1.` |
| 6 | 1 | upperLetter | `%2.` |
| 6 | 2 | lowerRoman | `%3.` |
| 7 | 0 | decimal | `제 %1 편` |
| 7 | 1 | decimal | `제 %2 장` |
| 7 | 2 | decimal | `제 %3 절` |
| 8 | 0 | decimal | `제 %1 편` |
| 8 | 1 | decimal | `제 %2 장` |
| 8 | 2 | decimal | `제 %3 절` |
| 9 | 0 | bullet | `□` |
| 9 | 1 | bullet | `` |
| 9 | 2 | bullet | `` |
| 10 | 0 | decimal | `%1` |
| 10 | 1 | decimal | `%1.%2` |
| 10 | 2 | decimal | `%1.%2.%3` |
| 11 | 0 | decimal | `%1` |
| 11 | 1 | decimal | `%1.%2` |
| 11 | 2 | decimal | `%1.%2.%3` |

> Pandoc은 markdown 리스트를 자체 numbering으로 출력합니다. 회사 양식의 
> 특정 numbering 정의(예: `제 1)`, `①`, `가.`)를 적용하려면 Word에서 List Paragraph 
> 스타일에 해당 numId를 바인딩하거나 별도 후처리가 필요합니다.

## Summary

| 상태 | 개수 | 처리 |
|---|---|---|
| exact (이미 일치) | 4 | none |
| case_mismatch (대소문자) | 9 | new style 추가 |
| semantic match (의미 매핑) | 12 | new style 추가 |
| user_override | 0 | new style 추가 |
| stub (디폴트 생성) | 8 | stub style 생성 |
| **missing (후보 없음)** | **10** | **skip** |

## Case mismatch → 추가

| severity | Pandoc 이름 | type | source 스타일 | new styleId |
|---|---|---|---|---|
| critical | `Heading 1` | paragraph | `heading 1` (id=`1`) | `Heading1` |
| critical | `Heading 2` | paragraph | `heading 2` (id=`2`) | `Heading2` |
| critical | `Heading 3` | paragraph | `heading 3` (id=`3`) | `Heading3` |
| important | `Heading 4` | paragraph | `heading 4` (id=`4`) | `Heading4` |
| important | `Heading 5` | paragraph | `heading 5` (id=`5`) | `Heading5` |
| important | `Heading 6` | paragraph | `heading 6` (id=`6`) | `Heading6` |
| optional | `Heading 7` | paragraph | `heading 7` (id=`7`) | `Heading7` |
| optional | `Heading 8` | paragraph | `heading 8` (id=`8`) | `Heading8` |
| optional | `Heading 9` | paragraph | `heading 9` (id=`9`) | `Heading9` |

## Semantic match → 추가

| severity | Pandoc 이름 | type | source 스타일 | new styleId |
|---|---|---|---|---|
| important | `Block Text` | paragraph | `Quote` (id=`a5`) | `BlockText` |
| optional | `Compact` | paragraph | `List Paragraph` (id=`a6`) | `Compact` |
| optional | `toc 1` | paragraph | `heading 1` (id=`1`) | `toc1` |
| optional | `toc 2` | paragraph | `heading 2` (id=`2`) | `toc2` |
| optional | `toc 3` | paragraph | `heading 3` (id=`3`) | `toc3` |
| optional | `toc 4` | paragraph | `heading 4` (id=`4`) | `toc4` |
| optional | `toc 5` | paragraph | `heading 5` (id=`5`) | `toc5` |
| optional | `toc 6` | paragraph | `heading 6` (id=`6`) | `toc6` |
| optional | `toc 7` | paragraph | `heading 7` (id=`7`) | `toc7` |
| optional | `toc 8` | paragraph | `heading 8` (id=`8`) | `toc8` |
| optional | `toc 9` | paragraph | `heading 9` (id=`9`) | `toc9` |
| critical | `Table` | table | `Table Grid` (id=`aa`) | `Table` |

## Stub (회사 템플릿에 없어 디폴트 생성)

| severity | Pandoc 이름 | type | new styleId | 적용 디폴트 |
|---|---|---|---|---|
| critical | `Source Code` | paragraph | `SourceCode` | 코드 블록: 고정폭 폰트 (Consolas 10pt) + 들여쓰기 |
| important | `Caption` | paragraph | `Caption` | 캡션: 가운데 정렬 + 이탤릭 9pt |
| optional | `Footnote Text` | paragraph | `FootnoteText` | 각주 본문: 9pt |
| optional | `Image Caption` | paragraph | `ImageCaption` | 이미지 캡션: Caption과 동일 |
| optional | `TOC Heading` | paragraph | `TOCHeading` | 목차 제목: 굵게 16pt |
| critical | `Verbatim Char` | character | `VerbatimChar` | 인라인 코드: 고정폭 폰트 (Consolas) + 회색 배경 |
| critical | `Hyperlink` | character | `Hyperlink` | 링크: 파란색 + 밑줄 (Word 기본 Hyperlink와 동일) |
| optional | `Footnote Reference` | character | `FootnoteReference` | 각주 번호: 윗첨자 |

## Missing (수동 처리 필요)

| severity | Pandoc 이름 | type | source 스타일 | new styleId |
|---|---|---|---|---|
| optional | `Body Text` | paragraph | — | — |
| optional | `First Paragraph` | paragraph | — | — |
| optional | `Author` | paragraph | — | — |
| optional | `Date` | paragraph | — | — |
| optional | `Abstract` | paragraph | — | — |
| optional | `Abstract Title` | paragraph | — | — |
| optional | `Bibliography` | paragraph | — | — |
| optional | `Verbatim Code` | paragraph | — | — |
| optional | `Figure` | paragraph | — | — |
| optional | `Captioned Figure` | paragraph | — | — |

## Exact (변경 없음)

| severity | Pandoc 이름 | type | source 스타일 | new styleId |
|---|---|---|---|---|
| critical | `Normal` | paragraph | `Normal` (id=`a`) | — |
| important | `Title` | paragraph | `Title` (id=`a3`) | — |
| optional | `Subtitle` | paragraph | `Subtitle` (id=`a4`) | — |
| important | `Default Paragraph Font` | character | `Default Paragraph Font` (id=`a0`) | — |
