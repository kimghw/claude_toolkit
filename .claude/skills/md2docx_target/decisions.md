# map 결정 기록 (decisions log)

본 스킬은 [`md2docx`](../md2docx/decisions.md) 의 매핑 정책을 그대로 공유한다. 본 문서는 `md2docx_target` 이 적용하는 결정만 요약하고, 변경된 부분(명명 규약, 게이트 정책)을 명시한다.

모든 결정은 `md2docx_target.py` 의 데이터 상수(`PANDOC_STYLES`, `SEMANTIC_HINTS`, `STUB_DEFINITIONS`)로 인코딩되어 있다.

---

## 결정 1: Pandoc 스타일 분류 — `PANDOC_STYLES`

Pandoc 이 output 에 참조하는 스타일을 **severity** 로 분류:

- **critical**: 누락 시 output 이 시각적으로 깨짐 (`Normal`, `Heading 1-3`, `Source Code`, `Verbatim Char`, `Hyperlink`, `Table`)
- **important**: 누락 시 일부 요소 무서식 (`Title`, `Block Text`, `Caption`, `Heading 4-6`)
- **optional**: 편의 스타일 (`Heading 7-9`, `Body Text`, `toc 1-9`, 등)

## 결정 2: 매칭 우선순위 — `find_mapping`

1. **user_override** — `--map` JSON (최우선)
2. **exact** — w:name 완전 일치 (변경 없음)
3. **case_mismatch** — 대소문자만 다름 → 새 스타일 추가
4. **semantic** — `SEMANTIC_HINTS` 의미 매칭 → 새 스타일 추가
5. **stub** — `STUB_DEFINITIONS` 디폴트 → stub 스타일 생성
6. **missing** — skip (리포트에만 기록)

## 결정 3: 의미 매핑 규칙 — `SEMANTIC_HINTS`

target 의 회사 어휘 ↔ Pandoc 어휘 매칭. 주요 항목:

| Pandoc 이름 | 매칭 후보 |
|---|---|
| `Block Text` | `Quote`, `Intense Quote`, `Blockquote`, `인용` |
| `Source Code` | `Code`, `Code Block`, `Preformatted Text` |
| `Caption` | `Image Caption`, `Figure Caption`, `Table Caption` |
| `Table` | `Table Grid`, `Normal Table`, `Plain Table 1` |
| `Verbatim Char` | `Code Char`, `Inline Code`, `Source Code Char` |
| `Hyperlink` | `Hyperlink`, `Internet Link`, `Link` |
| `Body Text` | `Body Text`, `본문` |
| `Compact` | `List Paragraph`, `Compact` |
| `toc 1~9` | `toc N`, `TOC N`, `heading N`, `Heading N` |

전문은 `md2docx_target.py` 의 `SEMANTIC_HINTS` 참조.

## 결정 4: Stub 디폴트 — `STUB_DEFINITIONS`

semantic 매칭이 실패하는 critical/important 스타일에 합리적 디폴트로 새 스타일 생성:

| 스타일 | type | 디폴트 | basedOn |
|---|---|---|---|
| `Verbatim Char` | character | Consolas + 회색 배경 | (없음) |
| `Hyperlink` | character | 파란색 + 밑줄 | (없음) |
| `Source Code` | paragraph | Consolas 10pt + 들여쓰기 | Normal |
| `Caption` | paragraph | 가운데 + 이탤릭 9pt | Normal |
| `Footnote Text` | paragraph | 9pt | Normal |
| `Footnote Reference` | character | 윗첨자 | (없음) |
| `Image Caption` | paragraph | Caption 과 동일 | Normal |
| `TOC Heading` | paragraph | 굵게 16pt | Heading 1 |

설계 원칙: 회사 본문(Normal) 과 시각적으로 구분되되 회사 양식을 해치지 않는다. Word 빌트인 색상·폰트와 일치.

## 결정 5: 정책적 제외

다음 스타일은 의도적으로 매핑하지 않는다:

- `Intense Quote`, `Intense Emphasis` — Pandoc 이 'intense' 개념을 사용하지 않음
- `header`, `footer` — Pandoc 은 머리글/바닥글을 sectPr 로 처리
- 헤딩 character 스타일 (`제목 N Char` 등) — Pandoc 은 character 변형 사용 안 함

필요 시 `--map` 으로 강제 매핑 가능.

---

## 결정 6: 명명 규약 — `<target_stem>_reference.docx` (`_reference` 접미사, stem 그대로)

본 스킬의 산출물은 다음 명명 규약을 따른다:

```
<cwd>/md2docx_target/<target_stem>_reference.docx
<cwd>/md2docx_target/<target_stem>_reference.report.md
```

- target 파일명 stem 뒤에 `_reference` 접미사를 붙인다 (접두사 추출/변형 없음)
- 분리자는 **언더스코어**(`_`) — md2docx 의 하이픈(`-`) 접두사 규약과 의도적으로 구분
- 어휘는 Pandoc 의 canonical 용어 `reference` 를 그대로 사용 (`--reference-doc` 입력 docx 임을 명시)

예:

| target | output |
|---|---|
| `mydoc.docx` | `mydoc_reference.docx` |
| `회사양식.docx` | `회사양식_reference.docx` |

근거: stem 변형 없이 단순 접미사 부착만으로 충분. 접미사 충돌은 실무에서 거의 발생하지 않아 추가 처리 로직 불필요 (사용자 결정 2026-05-18, 명명 어휘 `_ref` → `_reference` 갱신 2026-05-27).

---

## 결정 7: Numbering 정책 — 게이트 없음 (조용히 진행)

target 의 numbering.xml 에 list 정의(예: `1.`, `①`, `가.`)가 있어도 본 스킬은 **AskUserQuestion 을 호출하지 않는다.** 리포트의 "Numbering 정의" 섹션에 참고용으로만 표시하고 그대로 진행한다.

근거 (md2docx decisions.md 결정 8 의 기본값 채택):
- target 의 numbering 정의는 거의 항상 heading 전용 (제 N 편/장/절)
- markdown 리스트와 heading 은 시각·의미적으로 별개 요소
- 회사 list 양식이 별도로 존재해 markdown 리스트에 적용해야 한다면 `--map` JSON 으로 명시 지정해 재실행

본 스킬은 단일 기능 map 도구이므로 사용자 상호작용을 의도적으로 최소화한다 (사용자 결정 2026-05-18).

---

## md2docx 와 공유하는 결정 / 다른 결정

| 항목 | md2docx | md2docx_target |
|---|---|---|
| PANDOC_STYLES, SEMANTIC_HINTS, STUB_DEFINITIONS | 동일 | 동일 |
| 매칭 우선순위 | 동일 | 동일 |
| 정책적 제외 | 동일 | 동일 |
| 명명 규약 | `reference-<label>.docx` (하이픈 접두사) | `<target_stem>_reference.docx` (`_reference` 접미사, stem 그대로) |
| Numbering 게이트 | AskUserQuestion 3옵션 (rc=4) | **없음** (조용히 진행) |
| convert 후처리 | 포함 (lint, strip, postprocess, verify) | **없음** (map 만) |

---

## 변경 이력

- 2026-05-18 — 초기 작성. md2docx 의 매핑 정책 상수(PANDOC_STYLES / SEMANTIC_HINTS / STUB_DEFINITIONS) 그대로 채택. 명명은 stem 뒤 `_ref` 접미사(접두사 추출 없음). numbering 게이트 제거 (사용자 결정).
- 2026-05-27 — 명명 어휘 `_ref` → `_reference` 로 갱신 (사용자 요청). 산출물 폴더도 `<skill_dir>/output/` → `<cwd>/md2docx_target/` 으로 변경. md2docx 의 `template/` 캐시 명명도 동일하게 `_reference` 로 정렬.
