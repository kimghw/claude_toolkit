---
name: md2docx_layout
description: pandoc 으로 만든 output(.docx) 의 표·표간격·페이지·머리바닥 후처리 orchestrator. postprocess_tables / postprocess_table_spacing / postprocess_page / (옵션) postprocess_header_footer 를 md2docx_layout.py 가 subprocess 로 순차 호출. reference 미지정 시 md2docx/template/ 의 가장 최근 캐시 자동 사용. 기본 출력은 cwd/output/<stem>_output.docx (stem 의 '_pandoc' 접미사 자동 제거). 표 직후 단락 간격은 settings.json 에서 관리 (twips 단위, mode=ensure/insert/patch_existing/off). --header-source <src.docx> 지정 시 그 docx 의 텍스트 있는 가장 풍부한 header/footer 한 쌍을 default 로 박는다 (스타일·numbering 불변). 목록단락·표준 단락 pStyle ↔ target list 스타일 매핑(헤딩 제외)은 별도 md2docx_pstyle 스킬 사용.
---

# md2docx_layout — 표·표간격·페이지·머리바닥 후처리 orchestrator

## 목적

**pandoc 으로 만든 output(.docx) 의 회사 양식 후처리.** pandoc 의 reference-doc 전달만으로는 완전히 propagate 되지 않는 표 디자인(tblBorders/tblStylePr) 과 페이지 레이아웃(pgSz/pgMar) 을 reference 기반으로 강제 적용한다.

- 입력: `<input.docx>` (보통 [`md2docx`](../md2docx/SKILL.md) 가 만든 `cwd/pandoc/<stem>_pandoc.docx`)
- 출력: `cwd/output/<stem>_output.docx` (기본). `_pandoc` 접미사가 있으면 자동 제거.
- 본 스킬은 **자체 변환 로직 없는 orchestrator** — `postprocess_tables.py`, `postprocess_table_spacing.py`, `postprocess_page.py` 를 subprocess 로 순차 호출한다.

## 용어 (canonical)

| 용어 | 의미 |
|---|---|
| **input** | 후처리 대상 docx (보통 pandoc 출력) |
| **reference** | pandoc `--reference-doc` 으로 썼던 docx. 표 스타일·페이지 설정의 정답 소스 |
| **output** | 후처리 결과 docx |
| **postprocess_tables** | 표 디자인 patch (스타일 클론 + tblLook/cnfStyle + 최소 너비 + 단락 jc) |
| **postprocess_table_spacing** | 표 직후 단락 간격 강제 (settings.json 기반). 표와 다음 콘텐츠 사이에 spacing 박힌 빈 단락을 보장. |
| **postprocess_page** | 페이지 레이아웃 patch (pgSz/pgMar/cols/docGrid) |
| **postprocess_header_footer** | 머리글/바닥글 복제 (`--header-source` 지정 시만). 텍스트 있는 가장 풍부한 header/footer 각각 1 개씩 default 로 박음. 스타일·numbering·document.xml 본문 불변. |

## 인자 형식

| 호출 | 동작 |
|---|---|
| `md2docx_layout help` | 사용법 출력 |
| `md2docx_layout <input.docx>` | tables + table-spacing + page 후처리 (reference 자동) |
| `md2docx_layout <input.docx> --reference <ref.docx>` | reference 명시 |
| `md2docx_layout <input.docx> --header-source <src.docx>` | 머리글/바닥글 동기화 단계 추가 |
| `md2docx_layout <input.docx> --settings <path.json>` | 별도 settings.json 사용 (기본: skill/settings.json) |
| `md2docx_layout <input.docx> --out <out.docx>` | 출력 경로 지정 |
| `md2docx_layout <input.docx> --skip-tables` | tables 단계 생략 |
| `md2docx_layout <input.docx> --skip-table-spacing` | table-spacing 단계 생략 |
| `md2docx_layout <input.docx> --skip-page` | page 단계 생략 |

옵션:

| 플래그 | 설명 |
|---|---|
| `--reference <path>` | 표 스타일/페이지 설정의 소스 docx. 보통 `md2docx` 가 캐시한 `<target_stem>_ref.docx` |
| `--header-source <path>` | 머리글/바닥글을 가져올 별도 docx. `--reference` 와 의도적으로 분리 — 스타일은 안 가져오고 header/footer/media 만 가져온다. 미지정 시 머리바닥 단계 자체가 실행되지 않음. |
| `--settings <path>` | 표 직후 단락 간격 설정 (`post_table_spacing` 섹션) 을 담은 json 경로. 미지정 시 `.claude/skills/md2docx_layout/settings.json` 자동 사용. 파일 없으면 단계 자체가 no-op. |
| `--out <path>` | output 경로 (기본 `cwd/output/<stem>_output.docx`) |
| `--skip-tables` | postprocess_tables 호출 생략 (input 을 그대로 output 위치로 복사 후 나머지 단계) |
| `--skip-table-spacing` | postprocess_table_spacing 호출 생략 (표 직후 단락 간격 미변경) |
| `--skip-page` | postprocess_page 호출 생략 |

### 산출물 위치

- **output**: `cwd/output/<stem>_output.docx`
  - input stem 이 `_pandoc` 으로 끝나면 그 접미사를 제거 (`report_pandoc.docx` → `report_output.docx`)
  - `--out` 지정 시 그 경로 사용
- **input** 은 수정되지 않는다 (tables 단계가 별도 경로로 저장).

## reference 자동 탐색

`--reference` 미지정 시:

1. `.claude/skills/md2docx/template/*.docx` 중 가장 최근 수정된 (mtime) 파일 사용
2. 없으면:
   - `postprocess_page` 는 동기화 스킵 (페이지 변경 없음)
   - `postprocess_tables` 는 최소 patch 모드 (tblLook + cnfStyle 만, 스타일 클론 없음)

이 자동 탐색은 [`md2docx`](../md2docx/SKILL.md) 의 fallback 과 동일한 정책이라 보통 같은 reference 가 자동으로 잡힌다.

---

## 사용 도구

| 도구 | 용도 |
|:---|:---|
| `Bash` | `python .claude/skills/md2docx_layout/md2docx_layout.py ...` 실행 |

---

## 호출 예시

```powershell
# 표준 흐름 — md2docx 가 만든 pandoc/<stem>_pandoc.docx 를 후처리
python .claude\skills\md2docx_layout\md2docx_layout.py pandoc\report_pandoc.docx
# → cwd\output\report_output.docx
# → reference 는 .claude\skills\md2docx\template\ 가장 최근 캐시 자동 사용

# reference 명시
python .claude\skills\md2docx_layout\md2docx_layout.py pandoc\report_pandoc.docx ^
    --reference .claude\skills\md2docx\template\company_ref.docx

# 출력 경로 지정
python .claude\skills\md2docx_layout\md2docx_layout.py pandoc\report_pandoc.docx ^
    --out dist\report_final.docx

# tables 만 (page 생략)
python .claude\skills\md2docx_layout\md2docx_layout.py report.docx --skip-page

# 개별 스크립트 직접 호출도 가능
python .claude\skills\md2docx_layout\postprocess_tables.py report.docx --reference ref.docx
python .claude\skills\md2docx_layout\postprocess_page.py   report.docx --reference ref.docx
```

---

## 작동 흐름

```
[입력] <input.docx>  (보통 cwd/pandoc/<stem>_pandoc.docx)
   ↓
[reference 결정]
   ├─ --reference 시: 그 경로 사용
   └─ 미지정 시:      md2docx/template/*.docx 중 가장 최근 (mtime)
                       없으면 → page 스킵, tables 는 최소 patch 모드
   ↓
[1/N] postprocess_tables: input -> output 으로 저장
       (스타일 클론 + tblLook/cnfStyle + 최소 너비 + 단락 jc)
   ↓
[2/N] postprocess_table_spacing: output 에 in-place
       settings.json 의 post_table_spacing 섹션 기준으로 표 직후 단락의
       spacing(before/after/line) 강제. mode='ensure' (기본) 면 다음 sibling 이
       빈 단락이면 그 단락 spacing 박고, 아니면 새 빈 단락을 삽입한다.
   ↓
[3/N] postprocess_page: output 에 in-place
       (pgSz/pgMar/cols/docGrid 동기화)
   ↓
[4/N] postprocess_header_footer: output 에 in-place  (--header-source 시만)
       source 의 word/header*.xml, footer*.xml 중 텍스트 있는 가장 풍부한 한 개씩
       선정 → output 의 기존 header/footer 모두 제거 후 새것 1쌍 default 로 박음
       (스타일·numbering·document.xml 본문 불변, 미디어는 'hf_' 접두로 충돌 회피)
   ↓
[출력] cwd/output/<stem>_output.docx
```

N = 3 (기본) 또는 4 (--header-source 지정 시).

신호:
- `[1/N]`, `[2/N]`, `[3/N]`, `[4/N]` — 단계 표시
- 그 외는 호출한 서브 스크립트의 신호 통과 (`[POSTPROCESS]`, `[POSTPROCESS-CLONE]`, `[POSTPROCESS-PJC]`, `[POSTPROCESS-MINW]`, `[POSTPROCESS-TBLSP]`, `[POSTPROCESS-PAGE]`, `[POSTPROCESS-HF]`)

## settings.json — 표 직후 단락 간격 설정

기본 경로: `.claude/skills/md2docx_layout/settings.json`. `--settings <path>` 로 별도 파일 사용 가능. 파일 자체가 없거나 `enabled=false`/`mode=off` 면 표간격 단계는 no-op.

```json
{
  "post_table_spacing": {
    "enabled": true,
    "mode": "ensure",
    "spacing_before_twips": 0,
    "spacing_after_twips": 240,
    "line_twips": 240,
    "line_rule": "auto",
    "skip_nested_tables": true
  }
}
```

| 키 | 의미 |
|---|---|
| `enabled` | `false` 면 단계 자체가 no-op. 기본 `true`. |
| `mode` | `ensure`(기본) = 빈 단락이면 patch / 없으면 새 단락 삽입 ・ `insert` = 항상 삽입(중복 가능) ・ `patch_existing` = 빈 단락 있을 때만 patch ・ `off` = 비활성 |
| `spacing_before_twips` | 단락 앞 간격 (twips, 20twips=1pt). `null` 이면 속성 생략. |
| `spacing_after_twips` | 단락 뒤 간격 (twips). 240=12pt, 480=24pt, 120=6pt. |
| `line_twips` | 줄 간격 (`line_rule='auto'` 면 240ths-of-line, 240=single, 360=1.5, 480=double). `null` 가능. |
| `line_rule` | `auto`/`exact`/`atLeast`. `exact` 면 line_twips 단위는 twips(20ths-of-point). |
| `skip_nested_tables` | `true`(기본) 면 셀(`<w:tc>`) 안 nested 표의 뒤 단락은 안 건드림. 셀 끝 필수 단락이라 spacing 박으면 cell 높이 어긋남. |

단위 환산:
- 1pt = 20 twips, 1cm ≈ 567 twips
- 12pt = 240 twips (Word 기본 단락 뒤 간격)
- 24pt = 480 twips (강조용)
- 6pt = 120 twips (조밀)

---

## 의존 스킬과의 관계

```
md2docx (source + ref → output, pandoc 호출)
   ↓ output (cwd/pandoc/<stem>_pandoc.docx)
md2docx_layout (본 스킬 — 표·페이지 후처리)
   ↓ output (cwd/output/<stem>_output.docx)
md2docx_pstyle (목록단락·표준 pStyle ↔ target list 스타일 매핑 — 별도 스킬)
   ↓ output (cwd/output/<stem>_output.docx, in-place patch)
```

| 항목 | md2docx | md2docx_layout (본 스킬) | md2docx_pstyle |
|---|---|---|---|
| 입력 | source.md + reference 또는 target | output.docx + (reference) | output.docx + target.docx |
| 출력 | `cwd/pandoc/<stem>_pandoc.docx` | `cwd/output/<stem>_output.docx` | `<stem>_output.docx` (in-place) |
| pandoc 호출 | 예 | 아니오 (docx XML 직접 patch) | 아니오 (docx XML 직접 patch) |
| 단계 | lint+strip+(map)+convert | tables + page | scan + AskUserQuestion + apply |

**목록단락·표준 단락 pStyle ↔ target list 스타일 매핑(헤딩 제외) 은 본 스킬 범위 밖.** 별도 [`md2docx_pstyle`](../md2docx_pstyle/SKILL.md) 스킬 사용 — 이전에는 본 스킬의 `scan_lists.py` + `apply_lists.py` 가 유사한 기능을 했지만 폐기됐다. 새 사용자는 `md2docx_pstyle` 으로 바로 가면 됨.

---

## 관련 파일

- [`md2docx_layout.py`](./md2docx_layout.py) — orchestrator 진입점
- [`postprocess_tables.py`](./postprocess_tables.py) — 표 디자인 patch
- [`postprocess_table_spacing.py`](./postprocess_table_spacing.py) — 표 직후 단락 간격 강제 (settings.json 기반)
- [`postprocess_page.py`](./postprocess_page.py) — 페이지 레이아웃 patch
- [`postprocess_header_footer.py`](./postprocess_header_footer.py) — 머리글/바닥글 복제 (텍스트 있는 가장 풍부한 한 쌍 default 로 박음)
- [`settings.json`](./settings.json) — 표 직후 단락 간격 설정 (`post_table_spacing` 섹션)

## 자주 묻는 질문

**Q. input 의 stem 이 `_pandoc` 으로 끝나지 않으면?**
→ 그대로 stem 에 `_output` 만 부착. 예: `report.docx` → `cwd/output/report_output.docx`.

**Q. reference 가 없을 때도 후처리 효과가 있나?**
→ tables 는 최소 patch (tblLook + cnfStyle) 정도 효과만 있고 스타일 클론은 안 됨. page 는 완전히 스킵. 회사 양식 효과를 보려면 reference 가 필요하다.

**Q. md2docx 와 어떻게 chain 하나?**
→ md2docx 가 `cwd/pandoc/<stem>_pandoc.docx` 를 만들면, 이어서 `md2docx_layout cwd/pandoc/<stem>_pandoc.docx` 호출. reference 는 둘 다 `md2docx/template/` 최근 캐시를 fallback 으로 잡으므로 동일 reference 가 자동 적용된다.

**Q. 목록단락·표준 단락의 pStyle 이 회사(target) list 스타일대로 안 잡히면?**
→ 본 스킬은 표·페이지·머리바닥만 다룬다. `md2docx_pstyle scan` → AskUserQuestion (target list_styles 중 택1, 헤딩 제외) → `md2docx_pstyle apply` 흐름으로 처리한다. 이전 `scan_lists.py`/`apply_lists.py` 는 폐기됨.

**Q. `--reference` 와 `--header-source` 를 같은 파일로 줘도 되나?**
→ 가능. reference 는 styles·페이지 설정 추출에만, header-source 는 header/footer/media 복제에만 쓰이므로 같은 docx 를 줘도 충돌하지 않음. 다만 의도가 다른 두 출처(스타일은 회사 ref 에서, 머리바닥은 별도 양식에서)를 쓰고 싶다면 분리 지정.

**Q. `--header-source` 의 docx 에 header/footer 가 여러 개면 어떤 게 선택되나?**
→ word/header*.xml 중 `<w:t>` 안 비공백 문자 수가 가장 많은 한 개, footer 도 동일 기준. 빈 placeholder 나 로고만 있는 header (텍스트 없음) 는 자동 제외. 텍스트 있는 후보가 없으면 머리바닥 단계는 자동 스킵.

**Q. 머리바닥 동기화가 본문 스타일·numbering 을 건드릴 가능성은?**
→ 없음. `postprocess_header_footer` 는 word/document.xml 안 sectPr 의 `<w:headerReference>`/`<w:footerReference>` 만 갱신하고, styles.xml·numbering.xml 은 읽지도 쓰지도 않는다. 출력 docx 의 미디어와 충돌하지 않도록 source 미디어는 `hf_` 접두로 재명명된다.

**Q. 표 직후 간격을 12pt 가 아니라 24pt 로 더 떨어뜨리고 싶다.**
→ `.claude/skills/md2docx_layout/settings.json` 의 `post_table_spacing.spacing_after_twips` 를 `240` → `480` 으로 바꾸면 된다 (240=12pt, 480=24pt). 1pt=20twips. 본 스킬 다음 호출부터 자동 반영된다.

**Q. 표 직후 간격 설정을 프로젝트마다 다르게 쓰고 싶다.**
→ `--settings my_settings.json` 으로 별도 json 지정. 또는 skill 의 `settings.json` 자체를 프로젝트별로 수정. md2docx_layout 진입점에서 명시 인자 → skill 기본 → 둘 다 없으면 단계 no-op 순으로 fallback.

**Q. `--skip-table-spacing` 와 `settings.json` 의 `enabled=false` 차이?**
→ 둘 다 단계 건너뛰기 효과. 차이는 적용 범위 — `--skip-table-spacing` 은 그 호출에서만, `enabled=false` 는 settings.json 을 쓰는 모든 호출에서. 일회성 비활성은 플래그, 영구 비활성은 settings.json 권장.

**Q. 표 직후에 이미 빈 단락이 있는데 새 단락이 또 삽입되나? (mode='ensure')**
→ 아님. `ensure` 모드는 다음 sibling 이 빈 단락이면 그 단락의 `<w:pPr><w:spacing>` 만 patch 한다 (단락 추가 안 함). 비어있지 않은 단락이거나 아예 없는 경우(다음이 또 표/sectPr/문서 끝) 에만 새 빈 단락을 삽입. `insert` 모드는 항상 추가 (중복 가능).
