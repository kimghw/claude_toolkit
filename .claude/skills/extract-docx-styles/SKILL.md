---
name: extract-docx-styles
description: Pandoc `--reference-doc`용 Word(.docx) 템플릿의 스타일을 분석·검증·수정하여 Markdown→DOCX 변환 시 사용자 서식이 올바르게 적용되도록 돕는다. 한글 Word 템플릿의 style ID / w:name 매칭, 표(Table) 스타일 누락, reference.docx 준비가 필요한 상황에서 호출된다.
---

# extract-docx-styles — Pandoc reference.docx 스타일 추출·검증 가이드

Pandoc 변환 시 `--reference-doc` 옵션으로 Word 템플릿을 사용할 때, 사용자 서식이 올바르게 적용되도록 **템플릿의 스타일을 분석하고 필요한 경우 수정**한다.

---

## 핵심 원리

**Pandoc은 `w:styleId`가 아니라 `w:name`으로 스타일을 매칭한다.**

- ❌ 오해: Pandoc은 정해진 style ID(`Heading1`, `Normal`)가 필요하다
- ✅ 사실: Pandoc은 스타일의 `w:name` 속성을 본다

즉, 한글 Word가 자동 생성한 style ID(`1`, `a`, `a3` 등)여도 `w:name`이 `heading 1`, `Normal`, `Title` 등이면 정상 동작한다.

```xml
<w:style w:type="paragraph" w:styleId="1">
  <w:name w:val="heading 1"/>   <!-- Pandoc은 이 name을 봄 -->
</w:style>
```

---

## Pandoc이 찾는 `w:name` 목록

### 문단/텍스트 스타일

| Markdown 요소 | 필요한 w:name |
|--------------|--------------|
| 본문 | `Normal` |
| `#` ~ `######` | `heading 1` ~ `heading 6` |
| YAML `title:` | `Title` |
| YAML `subtitle:` | `Subtitle` |
| `>` 인용 | `Quote` |
| 블록 인용 | `Block Text` |
| 코드 블록 | `Source Code` 또는 `Verbatim Char` |
| 인라인 코드 | `Verbatim Char` |
| 링크 | `Hyperlink` |
| 이미지 캡션 | `Image Caption` |
| 표 캡션 | `Table Caption` |
| 각주 참조 | `Footnote Reference` |
| 각주 본문 | `Footnote Text` |
| 첫 문단 | `First Paragraph` |
| 리스트 간격 압축 | `Compact` |
| 이름 정의 | `Definition Term` |
| 내용 정의 | `Definition` |
| 저자 | `Author` |
| 날짜 | `Date` |
| 참고문헌 | `Bibliography` |
| 초록 | `Abstract` |
| 공통 캡션 | `Caption` |
| 그림 | `Figure` |

### 한글 Word UI 이름 → Pandoc w:name

| 한글 Word UI | Pandoc이 원하는 w:name |
|-------------|----------------------|
| 표준 | `Normal` |
| 제목 1 ~ 제목 6 | `heading 1` ~ `heading 6` |
| 제목 | `Title` |
| 부제 | `Subtitle` |
| 인용 | `Quote` |
| 강한 인용 | `Intense Quote` |
| 목록 단락 | `List Paragraph` |
| 머리글 | `header` |
| 바닥글 | `footer` |

> Word UI에 보이는 이름과 내부 `w:name`은 다를 수 있다. 한글 Word 기본 스타일은 내부적으로 영문 w:name을 유지하므로 보통 추가 작업 불필요.

---

## 작업 절차

**원칙**: 복잡한 grep/awk 파이프라인 대신 **unzip으로 XML만 꺼낸 뒤 `Read`·`Grep` 도구로 직접 읽고 판단**한다. 어떤 style ID가 표인지, Pandoc 필수 이름이 있는지는 XML을 눈으로(또는 Grep으로) 확인하면 된다.

### 1. docx 압축 해제

docx는 zip이므로 그대로는 Read 불가. `word/document.xml`과 `word/styles.xml`만 꺼내서 작업 폴더에 둔다.

```bash
TPL="references/templates/your-template.docx"
OUTDIR="references/templates/extracted/$(basename "$TPL" .docx)"
mkdir -p "$OUTDIR"
unzip -o "$TPL" word/document.xml word/styles.xml -d "$OUTDIR"
```

산출물: `<OUTDIR>/word/document.xml`, `<OUTDIR>/word/styles.xml` — 두 파일만 있으면 이후 판단은 Read/Grep으로 수행.

### 2. 실제 참조 중인 스타일 ID 찾기 (Grep 도구)

#### ⚠️ style ID는 불투명 문자열 — 두 파일을 교차 참조해 판단

한글 Word 템플릿의 style ID(`aa`, `10`, `1`, `a3` 등)는 **문자열만 봐서는 표/문단 구분 불가**. docx 내부 두 파일이 서로 다른 정보를 갖고 있으므로 **둘 다 참조해야** 어느 ID가 "실제 사용 중인 표 스타일"인지 확정된다.

| 파일 | 역할 | 제공하는 정보 |
|---|---|---|
| `word/document.xml` (본문) | **사용처** — 어디에 쓰이는지 | `<w:tblStyle w:val="aa"/>`처럼 참조하는 자리. 요소 이름(`pStyle`/`rStyle`/`tblStyle`)이 사용 문맥을 암시 |
| `word/styles.xml` (정의집) | **정체** — 실제 무엇인지 | `<w:style w:type="table" w:styleId="aa">…`의 `w:type` 속성(`paragraph`/`character`/`table`/`numbering`) |

**확정 규칙**: document.xml에서 `w:tblStyle`로 참조되는 ID ∩ styles.xml에서 `w:type="table"`로 정의된 ID = **실제 사용 중인 표 스타일**.

> 한쪽만 맞으면 의심할 것. 예: 정의는 `w:type="table"`인데 문서에서 한 번도 참조 안 됨 → 사용 안 되는 표 스타일. 반대로 참조는 있는데 정의가 없다 → 고아 참조(손상 가능성).

#### 1) document.xml에서 스타일 참조 수집

```
Grep 패턴: w:(pStyle|rStyle|tblStyle) w:val="[^"]+"
대상: <OUTDIR>/word/document.xml
output_mode: content
```

결과 예 (`w:tblStyle` 라인만 추리면 표 참조 후보):
```
w:pStyle w:val="1"         ← 문단 참조 후보
w:tblStyle w:val="aa"      ← 표 참조 후보 (document.xml 근거)
w:tblStyle w:val="10"      ← 표 참조 후보 (document.xml 근거)
```

빈도는 `count` 모드로 확인.

#### 2) styles.xml에서 해당 ID의 `w:type` 확인 → 최종 확정

3단계에서 각 후보 ID의 정의를 열어 `w:type="table"`인지 확인한다. 둘 다 일치하는 ID만 "실제 사용 중인 표 스타일"로 채택.

### 3. 해당 style ID의 실제 정의 확인 (Grep/Read)

2단계에서 얻은 ID들을 `styles.xml`에서 찾아 `w:name`·`basedOn`·`tblBorders` 등 실제 서식을 확인한다.

```
Grep 패턴: <w:style [^>]*w:styleId="aa"[^>]*>.*?</w:style>
multiline: true
대상: <OUTDIR>/word/styles.xml
output_mode: content
```

- `type="table"`이면 표 스타일 확정
- `w:name` 값이 Pandoc 필수 이름 목록([§Pandoc이 찾는 w:name](#pandoc이-찾는-wname-목록))과 일치하는지 점검
- 특히 `w:name="Table"`이 존재하는지 반드시 확인 (대부분 누락)

### 4. 누락된 w:name이 있으면 추가/수정

- 기존 스타일의 `w:name`을 Pandoc 규격으로 변경하거나
- 새 스타일을 추가할 때 `basedOn`으로 기존 스타일을 상속시키면 서식이 자동 적용됨
- 표의 경우 2단계에서 찾은 실제 사용 중인 표 style ID를 `basedOn`으로 지정 (아래 [§표(Table) 스타일](#️-table-스타일--가장-흔한-누락-지점) 참고)

---

### (선택) 요약 TSV로 저장하고 싶을 때

검토 결과를 파일로 남기고 싶으면 `<basename>.used_mapping.tsv`(reference/styleId/type/w:name/count) 형식으로 직접 작성. 자동 생성 스크립트는 불필요 — Grep 결과를 보고 손으로 정리하는 편이 한글 스타일 이름 인코딩 이슈도 피할 수 있음.

---

## ⚠️ 표(Table) 스타일 — 가장 흔한 누락 지점

Pandoc은 Markdown 표를 출력 docx에 다음처럼 기록한다:

```xml
<w:tblStyle w:val="Table"/>
```

→ 템플릿에 **`w:name="Table"`인 스타일이 없으면 표 서식이 전혀 적용되지 않는다**.

한글 Word 템플릿은 보통 `Normal Table`, `Table Grid`, 커스텀 ID(`aa` 등)만 있고 `Table`은 없다.

### 올바른 해결 절차

임의로 아무 표 스타일을 갖다 쓰지 말 것. **템플릿 안의 기존 표가 실제로 어떤 스타일을 쓰는지** 확인하고 그 스타일을 기반으로 `Table` 이름을 만든다.

#### 1단계: 템플릿 표가 실제로 사용하는 style ID 확인

```bash
unzip -p your-template.docx word/document.xml | grep -oE 'w:tblStyle w:val="[^"]+"' | sort | uniq -c
```

출력 예:
```
      3 w:tblStyle w:val="aa"        <- 주로 이걸 씀
      1 w:tblStyle w:val="10"
```

#### 2단계: 해당 style의 이름·서식 확인

```bash
unzip -p your-template.docx word/styles.xml | grep -oE '<w:style [^>]*w:styleId="aa"[^>]*>.{0,500}'
```

##### ⚠️ 사용 중인 표 스타일이 2개 이상이면 사용자에게 반드시 물어볼 것

Pandoc의 `Table`은 단 하나만 매칭되므로, 템플릿 안에 서로 다른 `w:tblStyle`이 2개 이상 사용 중이면 **LLM이 임의로 고르지 말고 사용자에게 확인한다.**

1. 각 표가 문서 내 **몇 번째 표**인지 (등장 순서), 해당 스타일의 **w:name·테두리·색상·밴드 여부** 등 서식 요약을 제시
2. "몇 번째 표의 스타일을 Markdown 표의 표준(`Table`의 `basedOn`)으로 사용할지" 명시적으로 질문
3. 사용자가 선택한 style ID를 `basedOn`으로 설정

제시 예시:
```
이 템플릿에는 사용 중인 표 스타일이 2개 있습니다:
  1번째 표 → styleId=aa (Table Grid): 검정색 굵은 테두리, 제목행 majorHA 폰트
  2번째 표 → styleId=10 (Plain Table 1): 연회색 얇은 테두리, 밴드행/밴드열
Markdown의 일반 표(|a|b|)를 몇 번째 표 서식으로 출력할지 골라주세요.
```

표 스타일 참조가 1개뿐이면 그대로 진행해도 된다.

#### 3단계: 그 스타일을 복제하여 이름만 `Table`로

`</w:styles>` 바로 앞에 삽입:

```xml
<w:style w:type="table" w:styleId="Table">
  <w:name w:val="Table"/>
  <w:basedOn w:val="aa"/>   <!-- 1단계에서 찾은 실제 사용 style ID -->
</w:style>
```

- `basedOn`으로 기존 스타일을 상속 → 테두리·배경·폰트 자동 적용
- `tblBorders` 같은 서식을 일일이 복사할 필요 없음

#### Word UI에서 하는 경우

1. 템플릿을 Word로 열기
2. 기존 표 클릭 → 디자인 탭에서 현재 적용된 스타일 확인
3. 스타일 갤러리에서 우클릭 → **복제**
4. 복제본 이름을 정확히 **`Table`**로 변경 후 저장

### 관련 표 이름

| Pandoc 요소 | w:name |
|-----------|--------|
| 표 본체 | `Table` (필수, 자주 누락) |
| 표 캡션 | `Table Caption` |
| 기본 테이블 | `Normal Table` |
| 테이블 그리드 | `Table Grid` |

---

## 권장 워크플로우

### A. 사용자 Word 템플릿 → reference.docx (권장)

```bash
cp my-korean-template.docx reference.docx
pandoc input.md --reference-doc=reference.docx -o output.docx
```

- Word에서 스타일 갤러리 → `제목 1`, `제목 2`, `표준` 우클릭 → 수정으로 커스터마이즈
- Style ID를 변경할 필요 없음

### B. Pandoc 기본 reference.docx에서 시작

```bash
pandoc -o reference.docx --print-default-data-file reference.docx
```

- Word로 열어 `Heading 1`, `Normal` 등 편집
- 영문 style ID이므로 한글 Word 사용자에겐 덜 직관적

---

## 하지 말아야 할 것

### ❌ Pandoc으로 docx를 "정규화"하지 말 것

```bash
# 이렇게 하면 사용자 템플릿 서식이 Pandoc 기본값으로 덮어써짐
pandoc user-template.docx -o normalized.docx
```

`--reference-doc` 없이 docx → docx 하면 Heading 색상·폰트 등이 모두 사라진다.

### ❌ styles.xml을 sed로 직접 편집 금지

- style ID를 `1` → `Heading1`로 rename해도 변화 없음 (w:name으로 매칭되므로)
- `document.xml`, `numbering.xml`, `settings.xml` 참조가 어긋나면 Word가 "손상된 파일"로 판정

### ❌ PowerShell `Compress-Archive`로 docx 재패키징 금지

Windows 경로 구분자(`\`)가 들어가 Word가 열지 못함. 반드시 forward slash(`/`) 사용:

```powershell
[System.IO.Compression.ZipFile]::Open($dst, 'Create')
# CreateEntry에 relPath.Replace('\\', '/') 적용
```

---

## 한글 Word style ID 매핑 참고

수동 매핑이 필요할 때만 참고(일반적으로 **불필요**):

| 한글 Word style ID | w:name | Pandoc 표준 |
|-------------------|--------|-------------|
| `a` | Normal | Normal |
| `1` ~ `9` | heading 1~9 | Heading1~9 |
| `1Char` ~ `9Char` | 제목 1 Char~ | Heading1Char~ |
| `a3` | Title | Title |
| `a4` | Subtitle | Subtitle |
| `a5` | Quote | Quote |
| `a6` | List Paragraph | ListParagraph |
| `Char` | 제목 Char | TitleChar |
| `Char0` | 부제 Char | SubtitleChar |
| `Char1` | 인용 Char | QuoteChar |
| `ab`, `ac` | header, footer | Header, Footer |
| `aa` | Table Grid | TableGrid |

**Pandoc 사용 자체에는 ID 매핑이 불필요. w:name만 맞으면 됨.**

---

## Windows Pandoc PATH 문제

Winget 설치 경로:
```
C:\Users\<username>\AppData\Local\Microsoft\WinGet\Packages\JohnMacFarlane.Pandoc_*\pandoc-<version>\pandoc.exe
```

### PATH 미등록 시

1. PowerShell 재시작
2. 현재 세션에 수동 추가:
   ```powershell
   $env:Path += ";C:\Users\<username>\AppData\Local\Microsoft\WinGet\Packages\JohnMacFarlane.Pandoc_*\pandoc-<version>"
   ```
3. 영구 등록:
   ```powershell
   [Environment]::SetEnvironmentVariable("Path",
     [Environment]::GetEnvironmentVariable("Path", "User") + ";<pandoc_경로>",
     "User")
   ```

---

## 실전 변환 패턴

```powershell
# 기본
pandoc input.md -o output.docx

# 커스텀 스타일
pandoc input.md --reference-doc=reference.docx -o output.docx

# 옵션 조합
pandoc input.md `
  --reference-doc=reference.docx `
  --toc --toc-depth=3 `
  -N `
  -o output.docx
```

---

## 요약: 가장 효율적인 경로

1. Word에서 원하는 스타일이 적용된 빈 문서 작성 (또는 기존 양식 활용)
2. 그 파일을 `reference.docx`로 저장
3. **docx 압축 해제** — `word/document.xml`·`word/styles.xml`만 꺼냄
4. **Grep 도구로 `w:tblStyle`·`w:pStyle` 참조 확인** → 실제 사용 중인 스타일 ID 파악 (표 여부 포함)
5. **Grep으로 해당 styleId의 정의 확인** → `w:name`이 Pandoc 규격과 맞는지, 특히 `Table`이 있는지 판단
6. 누락 있으면 `basedOn`으로 상속시켜 스타일 추가 → `pandoc input.md --reference-doc=reference.docx -o output.docx`

style ID 변경·XML 수술·정규화 같은 복잡한 작업 필요 없음.
