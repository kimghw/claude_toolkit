# Pandoc 스타일 매칭 리포트

- **Template**: `.claude\skills\md2docx\references\reference_reg.docx`
- **Total styles**: 39
- **By type**: character=18, numbering=1, paragraph=17, table=3

## Summary

| 상태 | 개수 |
|---|---|
| Exact match | 4 |
| Case mismatch (still works) | 9 |
| **Missing** | **30** |

## Missing Styles (Pandoc 폴백 발생)

### Critical (4)

| Pandoc 이름 | type | 유사 기존 스타일 (alias 후보) |
|---|---|---|
| `Source Code` | paragraph | — |
| `Verbatim Char` | character | `제목 1 Char`, `제목 2 Char`, `제목 3 Char`, `제목 4 Char`, `제목 5 Char`, `제목 6 Char`, `제목 7 Char`, `제목 8 Char`, `제목 9 Char`, `제목 Char`, `부제 Char`, `인용 Char`, `강한 인용 Char`, `머리글 Char`, `바닥글 Char` |
| `Hyperlink` | character | — |
| `Table` | table | `Normal Table`, `Table Grid`, `Plain Table 1` |

### Important (2)

| Pandoc 이름 | type | 유사 기존 스타일 (alias 후보) |
|---|---|---|
| `Block Text` | paragraph | — |
| `Caption` | paragraph | — |

### Optional (24)

| Pandoc 이름 | type | 유사 기존 스타일 (alias 후보) |
|---|---|---|
| `Body Text` | paragraph | — |
| `First Paragraph` | paragraph | `List Paragraph` |
| `Compact` | paragraph | — |
| `Author` | paragraph | — |
| `Date` | paragraph | — |
| `Abstract` | paragraph | — |
| `Abstract Title` | paragraph | `Title`, `Subtitle` |
| `Bibliography` | paragraph | — |
| `Verbatim Code` | paragraph | — |
| `Footnote Text` | paragraph | — |
| `Image Caption` | paragraph | — |
| `Figure` | paragraph | — |
| `Captioned Figure` | paragraph | — |
| `TOC Heading` | paragraph | `heading 1`, `heading 2`, `heading 3`, `heading 4`, `heading 5`, `heading 6`, `heading 7`, `heading 8`, `heading 9` |
| `toc 1` | paragraph | `heading 1` |
| `toc 2` | paragraph | `heading 2` |
| `toc 3` | paragraph | `heading 3` |
| `toc 4` | paragraph | `heading 4` |
| `toc 5` | paragraph | `heading 5` |
| `toc 6` | paragraph | `heading 6` |
| `toc 7` | paragraph | `heading 7` |
| `toc 8` | paragraph | `heading 8` |
| `toc 9` | paragraph | `heading 9` |
| `Footnote Reference` | character | `Intense Reference` |

## Case Mismatch (확인 권장)

| Pandoc 이름 | 템플릿 w:name | styleId | 비고 |
|---|---|---|---|
| `Heading 1` | `heading 1` | `1` | Found 'heading 1' — Word treats as alias; Pandoc may still match |
| `Heading 2` | `heading 2` | `2` | Found 'heading 2' — Word treats as alias; Pandoc may still match |
| `Heading 3` | `heading 3` | `3` | Found 'heading 3' — Word treats as alias; Pandoc may still match |
| `Heading 4` | `heading 4` | `4` | Found 'heading 4' — Word treats as alias; Pandoc may still match |
| `Heading 5` | `heading 5` | `5` | Found 'heading 5' — Word treats as alias; Pandoc may still match |
| `Heading 6` | `heading 6` | `6` | Found 'heading 6' — Word treats as alias; Pandoc may still match |
| `Heading 7` | `heading 7` | `7` | Found 'heading 7' — Word treats as alias; Pandoc may still match |
| `Heading 8` | `heading 8` | `8` | Found 'heading 8' — Word treats as alias; Pandoc may still match |
| `Heading 9` | `heading 9` | `9` | Found 'heading 9' — Word treats as alias; Pandoc may still match |

## Exact Matches

| Pandoc 이름 | styleId | severity |
|---|---|---|
| `Normal` | `a` | critical |
| `Title` | `a3` | important |
| `Subtitle` | `a4` | optional |
| `Default Paragraph Font` | `a0` | important |

## All Template Styles

| type | id | w:name | basedOn | default |
|---|---|---|---|---|
| character | `1Char` | `제목 1 Char` | `a0` |  |
| character | `2Char` | `제목 2 Char` | `a0` |  |
| character | `3Char` | `제목 3 Char` | `a0` |  |
| character | `4Char` | `제목 4 Char` | `a0` |  |
| character | `5Char` | `제목 5 Char` | `a0` |  |
| character | `6Char` | `제목 6 Char` | `a0` |  |
| character | `7Char` | `제목 7 Char` | `a0` |  |
| character | `8Char` | `제목 8 Char` | `a0` |  |
| character | `9Char` | `제목 9 Char` | `a0` |  |
| character | `Char` | `제목 Char` | `a0` |  |
| character | `Char0` | `부제 Char` | `a0` |  |
| character | `Char1` | `인용 Char` | `a0` |  |
| character | `Char2` | `강한 인용 Char` | `a0` |  |
| character | `Char3` | `머리글 Char` | `a0` |  |
| character | `Char4` | `바닥글 Char` | `a0` |  |
| character | `a0` | `Default Paragraph Font` | `` | Y |
| character | `a7` | `Intense Emphasis` | `a0` |  |
| character | `a9` | `Intense Reference` | `a0` |  |
| numbering | `a2` | `No List` | `` | Y |
| paragraph | `1` | `heading 1` | `a` |  |
| paragraph | `2` | `heading 2` | `a` |  |
| paragraph | `3` | `heading 3` | `a` |  |
| paragraph | `4` | `heading 4` | `a` |  |
| paragraph | `5` | `heading 5` | `4` |  |
| paragraph | `6` | `heading 6` | `a` |  |
| paragraph | `7` | `heading 7` | `a` |  |
| paragraph | `8` | `heading 8` | `a` |  |
| paragraph | `9` | `heading 9` | `a` |  |
| paragraph | `a` | `Normal` | `` | Y |
| paragraph | `a3` | `Title` | `a` |  |
| paragraph | `a4` | `Subtitle` | `a` |  |
| paragraph | `a5` | `Quote` | `a` |  |
| paragraph | `a6` | `List Paragraph` | `a` |  |
| paragraph | `a8` | `Intense Quote` | `a` |  |
| paragraph | `ab` | `header` | `a` |  |
| paragraph | `ac` | `footer` | `a` |  |
| table | `10` | `Plain Table 1` | `a1` |  |
| table | `a1` | `Normal Table` | `` | Y |
| table | `aa` | `Table Grid` | `a1` |  |

## Remediation 권장

**Critical 누락 우선 처리:**

- `Source Code` (paragraph) — 새 스타일 생성 필요
- `Verbatim Char` (character) — `제목 1 Char` 스타일에 alias 추가 권장 (Word: 스타일 수정 → 이름란에 `제목 1 Char,Verbatim Char`)
- `Hyperlink` (character) — 새 스타일 생성 필요
- `Table` (table) — `Normal Table` 스타일에 alias 추가 권장 (Word: 스타일 수정 → 이름란에 `Normal Table,Table`)

**대안:** toolkit의 `extract-docx-styles` 스킬 실행으로 자동 추가 가능. 위치: `c:\claude_toolkit\.claude\skills\extract-docx-styles\`
