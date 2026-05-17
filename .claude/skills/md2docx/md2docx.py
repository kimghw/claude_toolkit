#!/usr/bin/env python3
"""
md2docx — Markdown → DOCX 통합 진입점

인자 자동 분기:
    *.docx / *.doc                  → 매핑만, <원본명>_mapped.docx 저장
    *.md + *.docx                   → 매핑 + 변환, <원본md>.docx 저장
    --verify                        → 위 + XML/PDF 검증

내부적으로 map.py(매핑)와 verify.py(검증) + pandoc(변환)을 호출.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _subenv():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


HELP = """
md2docx — Markdown을 회사 양식 docx로 변환하는 통합 파이프라인

사용법
======

  python md2docx.py help                              사용법 출력
  python md2docx.py template <ref.docx>               reference 추출(매핑)만 수행
  python md2docx.py <input.md>                        template/ 목록 출력, 사용자 선택 필요
  python md2docx.py <input.md> --template <이름>      template/reference-<이름>.docx 으로 변환
  python md2docx.py <input.md> <ref.docx>             [기본] mapped + userlist-mapping 캐시가
                                                       있으면 자동 cached 모드 (lint/strip/userlist
                                                       질문 스킵). 캐시가 없으면 자동 fresh 모드
                                                       (모든 사용자 선택 진행).
  python md2docx.py renew <input.md> <ref.docx>       캐시 무시, 모든 사용자 선택을 다시 받음
  python md2docx.py <input.md> <ref.docx> --verify    위 + XML/PDF 검증

  하위 호환:
  python md2docx.py <ref.docx>                        (template 키워드 없이도 매핑만 수행)

  명명 규약: 매핑된 reference 는 항상 'reference-<label>.docx' 로 저장.
  label = 원본 ref 의 stem 에서 'reference_' 또는 'reference-' 접두사 제거 후 남는 값.
  예: reference_reg.docx → template/reference-reg.docx (label='reg')
      company.docx       → template/reference-company.docx (label='company')

인자
====

  <ref.docx>     회사 reference Word 템플릿 (.docx 또는 .dotx)
                 매핑 적용 결과는 항상 skill 의 template/ 폴더에
                 'reference-<label>.docx' 형식으로 저장된다 (재사용 가능한 pandoc
                 reference 카탈로그). label = 원본 stem 에서 reference[_-] 접두사 제거.
                 _mapping-report.md 는 input.md 가 함께 주어지면 작업 디렉토리(cwd) 에,
                 ref 만 주어진 매핑-only 모드라면 template/ 안에 저장된다.

  <input.md>     변환할 Markdown 파일.
                 산출물(<input>.docx, <input>_stripped.md, _mapping-report.md,
                 verify_out/) 은 <cwd>/<template_stem>/<md_stem>/ 폴더 안에
                 생성된다. template_stem 은 매핑된 reference 의 stem 에서
                 '_mapped' 접미사를 뺀 값. mapped reference 자체는 skill 의
                 template/ 폴더에 누적된다.

  --template <이름>
                 template/ 폴더에서 매핑된 reference 를 선택해 변환에 사용.
                 <이름> 은 label('reg'), 전체 stem('reference-reg'), 또는 파일명
                 ('reference-reg.docx') 모두 허용. 옛 규약('reference_reg_mapped') 호환.
                 <ref.docx> 와 동시 지정 불가.

  --verify       추가로 verify.py 호출. 매핑 적용/미적용 두 변환을 비교하고
                 XML 레벨 검증 + PDF 추출까지 수행.

  --skip-lint    lint 단계 건너뛰기. 사용자가 모호한 넘버링/heading 을
                 이미 확인했거나 무시하기로 한 뒤 재실행할 때 사용.

  --skip-strip   패턴 검출(strip_patterns.json) 단계 건너뛰기.
                 사용자가 모든 패턴을 유지하기로 결정했을 때 사용.

  --apply-strip <pid1,pid2,...>
                 선택된 패턴을 원본 .md (보존) 에 적용한 사본을
                 <md_stem>_stripped.md 로 저장하고, 그 파일을 입력으로 변환.
                 출력 docx 는 원본 stem 기준 (<원본>.docx).

  --no-postprocess
                 변환 후 표 디자인 post-processing 건너뛰기.
                 기본은 활성: pandoc 출력 docx 의 표에 reference 의 tblLook
                 (04A0) 과 셀별 cnfStyle 을 적용해 회사 양식 firstRow/firstCol
                 conditional 채움을 활성화한다.

  --out <file>   기본 출력 경로 덮어쓰기 (선택).

  --skip-userlist
                 사용자 정의 리스트 관찰·스캔·매핑 단계 모두 건너뛴다.
                 단, <output_dir>/userlist-mapping.json 이 이미 존재하면 후처리는 적용.

  --no-userlist  관찰·스캔·매핑·후처리 적용을 모두 건너뛴다 (해당 변환 한정 비활성).

  --reuse-userlist-mapping
                 <output_dir>/userlist-mapping.json 이 존재할 때 묻지 않고 그대로 사용.

  --fresh-userlist-mapping
                 <output_dir>/userlist-mapping.json 을 삭제 후 새 스캔·매핑 진행.

예시
====

  # 새 회사 양식 받았을 때 — 매핑만
  python md2docx.py company.docx
      → template/company_mapped.docx 생성 (Pandoc reference로 사용 가능)

  # 일상 변환 — template/ 에서 사용자 선택
  python md2docx.py report.md
      → template/ 목록 출력 후 returncode=4. Claude 가 사용자에게 묻고
        --template <이름> 으로 재실행.

  # 일상 변환 — 명시적 template 지정
  python md2docx.py report.md --template reference_reg
      → template/reference_reg_mapped.docx 사용해 report.docx 생성

  # 일상 변환 — ref.docx 명시 (매핑부터 새로)
  python md2docx.py report.md company.docx
      → template/company_mapped.docx 생성 후 report.docx 변환

  # 변환 + 시각 검증
  python md2docx.py report.md --template reference_reg --verify

  # 처음 보는 reference — 사용자 정의 리스트 관찰
  python md2docx.py report.md company.docx
      → [USERLIST-OBS] 줄 (표준 스타일 단락 머릿글 dump) + returncode=5
        Claude 가 observations 를 보고 후보를 직접 induction (□, ◌, (1), 등)
        AskUserQuestion 으로 각 후보에 unordered/ordered/사용 안 함 묻고
        template/userlist-<label>.json 을 Write 도구로 직접 작성한 뒤 재실행:

  python md2docx.py report.md company.docx
      → 캐시 파일 존재 → 1.55 자동 스킵, 변환 + 2.8 후처리 적용

  # 사용자 정의 리스트 기능을 이번 변환만 비활성화
  python md2docx.py report.md --template reference_reg --no-userlist
"""

# 매핑된 reference docx 누적 보관 폴더 (pandoc --reference-doc 카탈로그)
TEMPLATE_DIR = Path(__file__).resolve().parent / "template"


def list_templates() -> list[Path]:
    """template/ 안의 .docx (사용자 선택 가능 후보) 정렬 반환."""
    if not TEMPLATE_DIR.exists():
        return []
    return sorted(p for p in TEMPLATE_DIR.glob("*.docx") if p.is_file())


def reference_label(stem: str) -> str:
    """원본 ref stem 에서 'reference_' 또는 'reference-' 접두사를 제거한 라벨.
    이미 라벨이면 그대로 반환.
    예: 'reference_reg' → 'reg', 'reference-reg' → 'reg', 'company' → 'company'."""
    return re.sub(r"^reference[_\-]", "", stem, flags=re.IGNORECASE)


def mapped_filename_for(ref: Path) -> str:
    """매핑된 reference 의 표준 파일명: 'reference-<label>.docx'.

    template/ 카탈로그 명명 규약. 라벨은 원본 stem 에서 'reference[_-]' 접두사를 떼고
    남은 식별자 (예: reference_reg → reg, company → company)."""
    return f"reference-{reference_label(ref.stem)}.docx"


def resolve_template(name: str) -> Path | None:
    """--template <이름> → template/ 하위 파일 경로.

    표준 명명: 'reference-<label>.docx'. 사용자 입력으로 라벨만(`reg`) 줘도 자동 부착.
    허용:
      - 'reference-reg.docx'   (파일명)
      - 'reference-reg'        (stem)
      - 'reg'                  (라벨; reference- 자동 부착)
      - 옛 규약(`reference_reg_mapped.docx`, `reference_reg`) 도 호환.
    """
    if not TEMPLATE_DIR.exists():
        return None
    # 1) 파일명 그대로
    cand = TEMPLATE_DIR / name
    if cand.is_file():
        return cand
    # 2) stem + .docx
    cand = TEMPLATE_DIR / f"{name}.docx"
    if cand.is_file():
        return cand
    # 3) 라벨로 간주: reference-<label>.docx
    label = reference_label(name)
    cand = TEMPLATE_DIR / f"reference-{label}.docx"
    if cand.is_file():
        return cand
    # 4) 옛 규약 호환: <name>_mapped.docx
    cand = TEMPLATE_DIR / f"{name}_mapped.docx"
    if cand.is_file():
        return cand
    return None


def is_docx(p: Path) -> bool:
    return p.suffix.lower() in (".docx", ".dotx", ".doc")


def is_md(p: Path) -> bool:
    return p.suffix.lower() in (".md", ".markdown")


def get_mapped_path(ref: Path, out_dir: Path | None = None) -> Path:
    """매핑된 reference 의 출력 경로.

    명명 규약: 'reference-<label>.docx' (label = 원본 stem 에서 reference[_-] 접두사 제거).
    - ref 가 이미 그 형식이고 template/ 안에 있으면 그대로 사용 (재매핑 생략).
    - out_dir 가 주어지면 거기에 저장 (보통 template/).
    - out_dir 가 None 이면 ref 옆에 저장 (매핑-only 모드).

    옛 규약 호환: ref stem 이 '_mapped' 로 끝나면 그대로 사용 (재매핑 생략).
    """
    if ref.stem.endswith("_mapped"):
        return ref
    # ref 가 이미 reference-<label>.docx 형식이고 template/ 안에 있으면 그대로 (재매핑 생략).
    if ref.stem.startswith("reference-") and out_dir is not None and ref.parent.resolve() == out_dir.resolve():
        return ref
    name = mapped_filename_for(ref)
    if out_dir is not None:
        return out_dir / name
    return ref.with_name(name)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    args = sys.argv[1:]

    if not args or args[0].lower() in ("help", "-h", "--help"):
        print(HELP)
        return

    # 서브커맨드: 'template' (매핑만) / 'renew' (캐시 무시 + 모든 선택 재진행)
    subcommand = None
    if args and not args[0].startswith("-") and args[0].lower() in ("template", "renew"):
        subcommand = args[0].lower()
        args = args[1:]

    # 인자 파싱
    flags = {a for a in args if a.startswith("--")}
    out_override = None
    if "--out" in args:
        i = args.index("--out")
        if i + 1 < len(args):
            out_override = Path(args[i + 1])
            args = args[:i] + args[i + 2:]

    apply_strip_ids = []
    if "--apply-strip" in args:
        i = args.index("--apply-strip")
        if i + 1 < len(args):
            apply_strip_ids = [s for s in args[i + 1].split(",") if s.strip()]
            args = args[:i] + args[i + 2:]
        else:
            sys.exit("ERROR: --apply-strip 뒤에 쉼표 구분 패턴 id 목록이 필요합니다.")

    template_arg = None
    if "--template" in args:
        i = args.index("--template")
        if i + 1 < len(args):
            template_arg = args[i + 1]
            args = args[:i] + args[i + 2:]
        else:
            sys.exit("ERROR: --template 뒤에 template 이름이 필요합니다.")

    positional = [Path(a) for a in args if not a.startswith("--")]

    docx_files = [p for p in positional if is_docx(p)]
    md_files = [p for p in positional if is_md(p)]
    others = [p for p in positional if not (is_docx(p) or is_md(p))]

    if others:
        sys.exit(f"ERROR: 지원하지 않는 확장자: {[str(p) for p in others]}\n`md2docx help` 참고.")
    if len(docx_files) > 1:
        sys.exit(f"ERROR: reference.docx는 하나만 지정. 받은 것: {[str(p) for p in docx_files]}")
    if len(md_files) > 1:
        sys.exit(f"ERROR: markdown 파일은 하나만 지정. 받은 것: {[str(p) for p in md_files]}")
    if template_arg and docx_files:
        sys.exit("ERROR: --template 과 <ref.docx> 는 동시에 지정할 수 없습니다.")

    # --template 해석 → ref 로 승격
    if template_arg:
        if not md_files:
            sys.exit("ERROR: --template 은 <input.md> 와 함께 사용해야 합니다.")
        resolved = resolve_template(template_arg)
        if resolved is None:
            available = [p.name for p in list_templates()]
            sys.exit(
                f"ERROR: template/ 에서 '{template_arg}' 를 찾을 수 없습니다.\n"
                f"사용 가능한 template: {available or '(비어 있음)'}"
            )
        docx_files = [resolved]

    # md 만 있고 ref 가 없으면 — template/ 목록 출력 후 사용자 선택 필요
    if md_files and not docx_files:
        templates = list_templates()
        if not templates:
            sys.exit(
                "ERROR: template/ 폴더가 비어 있습니다.\n"
                "먼저 `md2docx <ref.docx>` 로 회사 reference 를 매핑해 template/ 에 mapped 파일을 만드세요."
            )
        print("[TEMPLATE-LIST] 사용 가능한 template 목록:")
        for t in templates:
            print(f"[TEMPLATE-OPTION] {t.name}")
        print()
        print("=" * 70)
        print("  사용자 선택 필요 — template/ 의 mapped reference 중 하나를 골라 재실행")
        print("=" * 70)
        print()
        print("  Claude 는 AskUserQuestion 으로 사용자에게 위 옵션 중 하나를 묻고")
        print("  다음과 같이 재실행해야 합니다:")
        print()
        print(f"    python md2docx.py {md_files[0]} --template <이름>")
        print()
        sys.exit(4)

    if not docx_files:
        sys.exit("ERROR: reference.docx 또는 --template 인자가 필요합니다.\n`md2docx help` 참고.")

    ref = docx_files[0]
    if not ref.exists():
        sys.exit(f"ERROR: 파일 없음: {ref}")

    here = Path(__file__).resolve().parent
    # mapped (pandoc reference) 산출물은 항상 skill 의 template/ 에 누적.
    # 변환 산출물(<input>.docx, _stripped.md, _mapping-report.md, verify_out/) 은
    # input.md 가 있으면 cwd/<template_stem>/<md_stem>/ 안에,
    # 아니면 template/ (매핑-only 모드의 report 위치).
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    work_dir = Path.cwd()
    mapped = get_mapped_path(ref, out_dir=TEMPLATE_DIR)

    # 변환 산출물 폴더: <cwd>/<template_stem>/<md_stem>/
    # template_stem 은 매핑된 reference 파일의 stem 에서 '_mapped' 접미사 제거한 값.
    template_stem = mapped.stem[:-len("_mapped")] if mapped.stem.endswith("_mapped") else mapped.stem
    if md_files:
        output_dir = work_dir / template_stem / md_files[0].stem
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = None

    # === 서브커맨드별 모드 결정 ===
    # template: 매핑만 (md 와 함께 줄 수 없음)
    # renew:    캐시 무시 + 모든 사용자 선택 재진행 (md+ref 필수)
    # 기본:     mapped + userlist-mapping 둘 다 존재하면 자동 cached, 아니면 자동 fresh
    cached_mode = False
    if subcommand == "template":
        if md_files:
            sys.exit("ERROR: 'template' 모드는 <ref.docx> 만 받습니다. md 파일은 함께 지정 불가.")
    elif subcommand == "renew":
        if not md_files:
            sys.exit("ERROR: 'renew' 모드는 <input.md> <ref.docx> 둘 다 필요합니다.")
        flags.add("--fresh-userlist-mapping")
        print(f"[모드] renew — 캐시 무시, 모든 사용자 선택을 재진행합니다.")
    elif md_files and output_dir is not None:
        mapping_json_path = output_dir / "userlist-mapping.json"
        if mapped.exists() and mapping_json_path.exists():
            cached_mode = True
            flags.add("--skip-lint")
            flags.add("--skip-strip")
            flags.add("--reuse-userlist-mapping")
            print(f"[모드] cached — mapped + userlist-mapping 캐시 존재, lint/strip/userlist 질문 자동 스킵")
            print(f"        매핑된 reference: {mapped}")
            print(f"        userlist-mapping: {mapping_json_path}")
            print(f"        모든 설정을 다시 선택하려면: md2docx renew <md> <ref.docx>")
        else:
            print(f"[모드] fresh — 캐시 없음 (mapped 존재={mapped.exists()}, "
                  f"mapping 존재={mapping_json_path.exists()}), 처음부터 사용자 선택 진행")

    # === Step 1: 매핑 ===
    if mapped == ref:
        print(f"[1/?] 이미 매핑된 파일로 보임 (이름에 _mapped 포함): {ref}")
        print(f"      매핑 단계 건너뜀.")
    elif cached_mode and mapped.exists():
        print(f"[1/?] 매핑 캐시 사용 (cached 모드): {mapped}")
        print(f"      재매핑하려면 'renew' 또는 mapped 파일 삭제 후 재실행")
    else:
        print(f"[1/?] 매핑 적용: {ref.name} -> {mapped.name}")
        # 리포트는 파일로 저장 — stdout 인코딩 이슈 회피
        # 변환 모드(md 있음) 면 output_dir, 매핑-only 면 template/ 에.
        report_dir = output_dir if output_dir is not None else mapped.parent
        report_path = report_dir / "_mapping-report.md"
        result = subprocess.run(
            [sys.executable, str(here / "map.py"), str(ref),
             "--apply", str(mapped), "--out", str(report_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        if result.returncode != 0 or not mapped.exists():
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            sys.exit(f"ERROR: map.py 실패 (returncode={result.returncode})")
        # [APPLY]/[NUMBERING] 줄만 추출 (영문이라 안전)
        has_numbering = False
        for line in result.stdout.splitlines():
            if line.startswith("[APPLY]") or line.startswith("[NUMBERING]"):
                print(f"      {line}")
                if line.startswith("[NUMBERING]"):
                    has_numbering = True
        print(f"      리포트: {report_path}")
        if has_numbering:
            print()
            print(f"  >> 회사 reference에 numbering 정의가 있습니다.")
            print(f"  >> markdown 리스트 (1./2./-) 에 회사 양식을 적용할지 사용자에게 확인 필요.")
            print(f"  >> 자세한 정의는 리포트의 'Numbering 정의' 섹션 참고.")

    if not md_files:
        print()
        print(f"완료. Pandoc reference로 사용 가능: {mapped}")
        print(f"  pandoc input.md -o output.docx --reference-doc={mapped}")
        return

    md = md_files[0]
    if not md.exists():
        sys.exit(f"ERROR: 파일 없음: {md}")

    # === Step 1.55: 사용자 정의 리스트 — catalog 관찰 + mapping 재사용/새로 분석 ===
    # 두 개의 JSON 으로 관심사 분리:
    #   1) template/userlist-<label>.json   per-reference cluster 카탈로그 (정의만)
    #   2) <output_dir>/userlist-mapping.json   per-conversion (list_kind → cluster_id)
    # Step 1.55 는 (1) 의 존재만 보장하고, (2) 가 이미 있으면 reuse/fresh 묻는다.
    # 실제 (2) 의 list_rules 작성은 Step 2.85 (pandoc 변환 직후 스캔) 에서 수행.
    label = reference_label(ref.stem)
    catalog_json = TEMPLATE_DIR / f"userlist-{label}.json"
    observations_json = TEMPLATE_DIR / f"_userlist-{label}-observations.json"
    mapping_json = output_dir / "userlist-mapping.json"

    if "--no-userlist" in flags or "--skip-userlist" in flags:
        # 관찰/스캔/매핑/후처리 모두 비활성.
        pass
    else:
        # (A) catalog 부재 시 관찰 단계 실행 (Claude 에게 cluster 정의 작성을 위임).
        if not catalog_json.exists():
            print()
            print(f"[1.55/?] 사용자 정의 리스트 관찰 (cluster catalog 생성): {mapped.name}")
            ext_result = subprocess.run(
                [sys.executable, str(here / "userlist_extract.py"), str(mapped),
                 "--out", str(observations_json)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                env=_subenv(),
            )
            for line in ext_result.stdout.splitlines():
                if line.startswith("[USERLIST"):
                    print(f"      {line}")
            if ext_result.stderr.strip():
                print(ext_result.stderr, file=sys.stderr)

            if ext_result.returncode == 5:
                print()
                print("=" * 70)
                print("  reference 의 표준 스타일 단락 머릿글 관찰 — Claude 가 cluster catalog 작성 필요")
                print("=" * 70)
                print()
                print("  Claude 는 [USERLIST-OBS] cluster 들을 직접 induction 한 뒤:")
                print()
                print("    1) 머릿글 글리프, 들여쓰기(left/hanging/firstLine), 폰트 일관성으로 진짜 list 후보만 선별")
                print("    2) 일회성·prose·표 셀은 제외")
                print(f"    3) Write 도구로 catalog 작성: {catalog_json}")
                print()
                print("  catalog JSON 구조 (per-reference cluster 정의만; apply_to 같은 매핑 결정 없음):")
                print('    {"reference": "<ref>.docx", "label": "<label>", "clusters": [')
                print('      {"id": "<human-readable>", "head_normalized": "□",')
                print('       "marker_sequence": ["□"]  // bullet 형이면 글리프 1개, ordered 형이면 ["①","②",...]')
                print('       "indent": {...}, "spacing": {...}, "jc": "...", "rPr": {...},')
                print('       "pPr_xml": "<w:pPr>...</w:pPr>", "rPr_xml": "<w:rPr>...</w:rPr>"}]}')
                print(f"    (pPr_xml/rPr_xml 은 {observations_json.name} 의 해당 cluster 에서 그대로 복사.)")
                print()
                print("  작성 후 같은 명령으로 재실행 (catalog 발견 → 관찰 자동 스킵):")
                print(f"    python md2docx.py <md> <ref.docx>")
                print()
                print("  cluster 가 없으면 catalog 를 빈 clusters: [] 로 작성하거나 --skip-userlist 로 진행")
                print()
                sys.exit(5)
            elif ext_result.returncode != 0:
                print(f"      [USERLIST-WARN] userlist_extract.py returncode={ext_result.returncode} — 무시하고 진행")
            # returncode == 0 → 관찰 0건. catalog 만들지 않고 진행 (다음 호출도 빠른 0 종료).

        # (B) catalog 가 있고 mapping 도 있으면 reuse/fresh 묻기.
        if catalog_json.exists() and mapping_json.exists():
            if "--fresh-userlist-mapping" in flags:
                try:
                    mapping_json.unlink()
                    print()
                    print(f"[1.55/?] userlist-mapping.json 삭제 (--fresh-userlist-mapping) — 단계 2.85 에서 재스캔")
                except OSError:
                    pass
            elif "--reuse-userlist-mapping" in flags:
                print()
                print(f"[1.55/?] userlist-mapping.json 재사용 (--reuse-userlist-mapping): {mapping_json}")
            else:
                # 사용자에게 reuse/fresh 묻기.
                print()
                print(f"[USERLIST-MAPPING-EXISTS] {mapping_json}")
                print()
                print("=" * 70)
                print("  이전 변환의 userlist 매핑 캐시 발견 — 사용자 확인 필요")
                print("=" * 70)
                print()
                print(f"  파일: {mapping_json}")
                print()
                print("  Claude 는 AskUserQuestion 으로 다음 셋 중 하나를 사용자에게 묻기:")
                print("    - 재사용 — 저장된 매핑 그대로 사용 (--reuse-userlist-mapping 추가 후 재실행)")
                print("    - 새로 분석 — 캐시 삭제 후 단계 2.85 에서 다시 스캔/질문 (--fresh-userlist-mapping)")
                print("    - 매핑 비활성 — 이번 변환 후처리 건너뛰기 (--no-userlist 추가 후 재실행)")
                print()
                sys.exit(6)

    # === Step 1.6: Markdown lint (넘버링/heading 사전 검토) ===
    if "--skip-lint" not in flags:
        print()
        print(f"[1.6/?] Markdown lint: {md.name}")
        lint_result = subprocess.run(
            [sys.executable, str(here / "lint.py"), str(md)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        for line in lint_result.stdout.splitlines():
            if line.startswith("[LINT"):
                print(f"      {line}")
        if lint_result.stderr.strip():
            print(lint_result.stderr, file=sys.stderr)

        if lint_result.returncode == 2:
            print()
            print("=" * 70)
            print("  모호한 넘버링/heading 기호 감지 — 사용자 확인 필요")
            print("=" * 70)
            print()
            print("  변환을 진행하기 전에 위 [LINT-AMBIGUOUS] 항목을 확인해야 합니다.")
            print("  Claude 는 AskUserQuestion 으로 사용자에게 어느 스타일을 사용할지")
            print("  묻고, 다음 중 하나로 처리해야 합니다:")
            print()
            print("    1) .md 파일을 수정해 모호성을 제거한 뒤 재실행")
            print("    2) 그대로 진행하려면 --skip-lint 추가해 재실행")
            print()
            sys.exit(2)
        elif lint_result.returncode != 0:
            print(f"      [LINT-WARN] lint.py returncode={lint_result.returncode} — 무시하고 진행")

    # === Step 1.7: 패턴 검출 / 적용 (references/strip_patterns.json) ===
    original_md = md
    if apply_strip_ids:
        # 선택된 패턴을 원본에 적용 → output_dir 에 <stem>_stripped.md 생성, 변환 입력으로 사용
        stripped = output_dir / (md.stem + "_stripped" + md.suffix) if not md.stem.endswith("_stripped") else md
        print()
        print(f"[1.7/?] 패턴 적용: {md.name} -> {stripped.name}  (패턴: {', '.join(apply_strip_ids)})")
        strip_result = subprocess.run(
            [sys.executable, str(here / "strip.py"), str(md),
             "--apply", *apply_strip_ids, "--out", str(stripped)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        for line in strip_result.stdout.splitlines():
            if line.startswith("[STRIP"):
                print(f"      {line}")
        if strip_result.returncode != 0:
            print(strip_result.stderr, file=sys.stderr)
            sys.exit(f"ERROR: strip.py --apply 실패 (returncode={strip_result.returncode})")
        md = stripped  # pandoc 입력을 stripped 사본으로 전환 (원본은 보존)
    elif "--skip-strip" not in flags:
        print()
        print(f"[1.7/?] 패턴 검출: {md.name}")
        strip_result = subprocess.run(
            [sys.executable, str(here / "strip.py"), str(md), "--reference", str(mapped)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        for line in strip_result.stdout.splitlines():
            if line.startswith("[STRIP") or line.startswith("  "):
                print(f"      {line}")
        if strip_result.stderr.strip():
            print(strip_result.stderr, file=sys.stderr)

        if strip_result.returncode == 3:
            print()
            print("=" * 70)
            print("  회사 양식과 충돌 가능한 패턴 매칭 — 사용자 확인 필요")
            print("=" * 70)
            print()
            print("  원본 .md 는 보존됩니다. Claude 는 위 [STRIP-MATCH] 각 패턴에 대해")
            print("  AskUserQuestion 으로 사용자에게 제거 여부를 묻고:")
            print()
            print("    - 제거할 패턴 ID 들을 쉼표로 모아 다음 명령으로 재실행:")
            print(f"        python md2docx.py <md> <ref.docx> --apply-strip <pid1>,<pid2>")
            print(f"      (원본 보존, <md_stem>_stripped.md 생성 후 변환)")
            print()
            print("    - 모두 유지: --skip-strip 추가해 재실행")
            print()
            sys.exit(3)
        elif strip_result.returncode != 0:
            print(f"      [STRIP-WARN] strip.py returncode={strip_result.returncode} — 무시하고 진행")

    # === Step 2: 변환 ===
    # 출력 docx 위치: (1) --out 지정, (2) 없으면 output_dir / <원본 .md stem>.docx
    out = out_override if out_override else output_dir / (original_md.stem + ".docx")
    print()
    print(f"[2/?] 변환: {md.name} -> {out.name}")
    result = subprocess.run(
        ["pandoc", str(md), "-o", str(out), f"--reference-doc={mapped}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(f"ERROR: pandoc 실패")
    print(f"      OK ({out.stat().st_size} bytes)")

    # === Step 2.5: 표 디자인 post-processing ===
    if "--no-postprocess" not in flags:
        print()
        print(f"[2.5/?] 표 post-processing: {out.name}")
        pp_result = subprocess.run(
            [sys.executable, str(here / "postprocess_tables.py"), str(out),
             "--reference", str(mapped)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        for line in pp_result.stdout.splitlines():
            if line.startswith("[POSTPROCESS"):
                print(f"      {line}")
        if pp_result.returncode != 0:
            print(pp_result.stderr, file=sys.stderr)
            print(f"      [POSTPROCESS-WARN] returncode={pp_result.returncode} — 변환 결과는 유지")

    # === Step 2.6: 페이지 레이아웃 post-processing ===
    if "--no-postprocess" not in flags:
        print()
        print(f"[2.6/?] 페이지 post-processing: {out.name}")
        pp_page_result = subprocess.run(
            [sys.executable, str(here / "postprocess_page.py"), str(out),
             "--reference", str(mapped)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        for line in pp_page_result.stdout.splitlines():
            if line.startswith("[POSTPROCESS-PAGE"):
                print(f"      {line}")
        if pp_page_result.returncode != 0:
            print(pp_page_result.stderr, file=sys.stderr)
            print(f"      [POSTPROCESS-PAGE-WARN] returncode={pp_page_result.returncode} — 변환 결과는 유지")

    # === Step 2.65: style-참조 numbering 복원 (heading 자동 번호 복구) ===
    # pandoc 이 numbering.xml 을 재작성하면서 회사 style 정의가 참조하는 numId 가
    # 사라진다. reference 의 numbering.xml 에서 해당 num + abstractNum 정의를
    # 복사해 출력에 주입한다 (heading 1 → "제 %1 편" 같은 자동 번호 복구).
    if "--no-postprocess" not in flags:
        print()
        print(f"[2.65/?] style-참조 numbering 복원: {out.name}")
        pp_num_result = subprocess.run(
            [sys.executable, str(here / "postprocess_style_numbering.py"), str(out),
             "--reference", str(mapped)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        for line in pp_num_result.stdout.splitlines():
            if line.startswith("[POSTPROCESS-STYLE-NUM"):
                print(f"      {line}")
        if pp_num_result.returncode != 0:
            print(pp_num_result.stderr, file=sys.stderr)
            print(f"      [POSTPROCESS-STYLE-NUM-WARN] returncode={pp_num_result.returncode} — 변환 결과는 유지")

    # === Step 2.66: customStyle basedOn 체인 인라인 베이킹 ===
    # map.py 가 만든 매핑 스타일은 basedOn 만 갖고 pPr/rPr 은 부모에서 상속받게 둔다.
    # Word 가 customStyle 의 basedOn 체인 시각 상속을 일부 적용하지 못해 회사 양식
    # (자동 번호·정렬·굵게·크기) 이 단락에 안 보이는 경우가 있다. 체인 전체의
    # pPr/rPr 자식을 leaf 스타일에 인라인으로 박아 self-contained 로 만든다.
    if "--no-postprocess" not in flags:
        print()
        print(f"[2.66/?] customStyle basedOn 체인 인라인 베이킹: {out.name}")
        pp_inline_result = subprocess.run(
            [sys.executable, str(here / "postprocess_inline_basedon.py"), str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        for line in pp_inline_result.stdout.splitlines():
            if line.startswith("[POSTPROCESS-INLINE-BASEDON"):
                print(f"      {line}")
        if pp_inline_result.returncode != 0:
            print(pp_inline_result.stderr, file=sys.stderr)
            print(f"      [POSTPROCESS-INLINE-BASEDON-WARN] returncode={pp_inline_result.returncode} — 변환 결과는 유지")

    # === Step 2.67: document.xml 의 case_mismatch alias pStyle 을 회사 원본 styleId 로 치환 ===
    # Word 스타일 갤러리/스타일 표시 패널에서 회사 원본 항목(예: "제 1 편 제목") 이
    # 하이라이트되도록 단락의 pStyle 을 customStyle alias (Heading1) → 원본 styleId (1) 로
    # 정규화. 시각 효과는 그대로 (basedOn 체인이 같은 정의를 가리키므로).
    if "--no-postprocess" not in flags:
        print()
        print(f"[2.67/?] pStyle 정규화 (alias → 회사 원본 styleId): {out.name}")
        pp_remap_result = subprocess.run(
            [sys.executable, str(here / "postprocess_remap_pstyle.py"), str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        for line in pp_remap_result.stdout.splitlines():
            if line.startswith("[POSTPROCESS-REMAP-PSTYLE"):
                print(f"      {line}")
        if pp_remap_result.returncode != 0:
            print(pp_remap_result.stderr, file=sys.stderr)
            print(f"      [POSTPROCESS-REMAP-PSTYLE-WARN] returncode={pp_remap_result.returncode} — 변환 결과는 유지")

    # === Step 2.7: bullet/머릿기호 단락 (numPr) 에 reference 의 list paragraph 속성 적용 ===
    if "--no-postprocess" not in flags:
        print()
        print(f"[2.7/?] 리스트 단락 post-processing: {out.name}")
        pp_list_result = subprocess.run(
            [sys.executable, str(here / "postprocess_lists.py"), str(out),
             "--reference", str(mapped)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        for line in pp_list_result.stdout.splitlines():
            if line.startswith("[POSTPROCESS-LISTS"):
                print(f"      {line}")
        if pp_list_result.returncode != 0:
            print(pp_list_result.stderr, file=sys.stderr)
            print(f"      [POSTPROCESS-LISTS-WARN] returncode={pp_list_result.returncode} — 변환 결과는 유지")

    # === Step 2.85: pandoc 출력의 numPr list_kind 스캔 + mapping 미생성 시 사용자 확인 ===
    # mapping_json 이 없으면 pandoc output 을 스캔해 (numFmt, ilvl) list_kind 를 dump 한다.
    # Claude 가 catalog 의 cluster 후보를 함께 보여주며 사용자에게 list_kind 별 cluster 선택을
    # 물어, Write 도구로 mapping_json 을 작성한 뒤 재실행하도록 한다.
    scan_json = output_dir / "_userlist-pandoc-scan.json"
    if (
        "--no-userlist" not in flags
        and "--no-postprocess" not in flags
        and "--skip-userlist" not in flags
        and catalog_json.exists()
        and not mapping_json.exists()
    ):
        print()
        print(f"[2.85/?] pandoc 출력 list_kind 스캔: {out.name}")
        scan_result = subprocess.run(
            [sys.executable, str(here / "userlist_scan_lists.py"), str(out),
             "--out", str(scan_json)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        for line in scan_result.stdout.splitlines():
            if line.startswith("[USERLIST"):
                print(f"      {line}")
        if scan_result.stderr.strip():
            print(scan_result.stderr, file=sys.stderr)

        if scan_result.returncode == 7:
            print()
            print("=" * 70)
            print("  pandoc 출력의 list_kind 매핑 — Claude + 사용자 확인 필요")
            print("=" * 70)
            print()
            print(f"  catalog (cluster 정의): {catalog_json}")
            print(f"  스캔 결과:               {scan_json}")
            print()
            print("  Claude 는 catalog 의 cluster 들과 위 [USERLIST-PANDOC-LIST] list_kind 들을")
            print("  함께 보여주며 사용자에게 list_kind 마다 어떤 cluster 를 적용할지 묻기")
            print("  (AskUserQuestion 의 옵션: catalog 의 각 cluster_id 또는 '사용 안 함').")
            print()
            print("  답을 모은 뒤 Write 도구로 다음 파일 작성:")
            print(f"    {mapping_json}")
            print()
            print("  mapping JSON 구조:")
            print('    {"md": "<md filename>", "reference_label": "<label>", "list_rules": [')
            print('      {"match": {"numFmt": "bullet", "ilvl": "0"}, "cluster_id": "<id from catalog>"},')
            print('      {"match": {"numFmt": "bullet", "ilvl": "1"}, "cluster_id": "<another id>"},')
            print('      {"match": {"numFmt": "decimal", "ilvl": "0"}, "cluster_id": null}  // 사용 안 함')
            print('    ]}')
            print()
            print("  작성 후 같은 명령으로 재실행 (mapping 발견 → 단계 2.85 스킵 → 2.86 후처리):")
            print(f"    python md2docx.py <md> <ref.docx>")
            print()
            sys.exit(7)
        elif scan_result.returncode != 0:
            print(f"      [USERLIST-SCAN-WARN] returncode={scan_result.returncode} — 매핑 단계 스킵")

    # === Step 2.86: 사용자 정의 리스트 cluster 패턴 적용 (postprocess_userlist.py) ===
    if (
        "--no-userlist" not in flags
        and "--no-postprocess" not in flags
        and catalog_json.exists()
        and mapping_json.exists()
    ):
        print()
        print(f"[2.86/?] 사용자 정의 리스트 후처리: {out.name}")
        print(f"          catalog={catalog_json.name}  mapping={mapping_json.name}")
        pp_ul_result = subprocess.run(
            [sys.executable, str(here / "postprocess_userlist.py"), str(out),
             "--catalog", str(catalog_json), "--mapping", str(mapping_json)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        for line in pp_ul_result.stdout.splitlines():
            if line.startswith("[POSTPROCESS-USERLIST"):
                print(f"      {line}")
        if pp_ul_result.returncode != 0:
            print(pp_ul_result.stderr, file=sys.stderr)
            print(f"      [POSTPROCESS-USERLIST-WARN] returncode={pp_ul_result.returncode} — 변환 결과는 유지")

    # === Step 3: verify (옵션) ===
    if "--verify" in flags:
        verify_dir = output_dir / "verify_out"
        print()
        print(f"[3/?] 검증 (XML + PDF): {verify_dir}")
        result = subprocess.run(
            [sys.executable, str(here / "verify.py"), str(md),
             "--mapped-ref", str(mapped), "--out-dir", str(verify_dir)],
            text=True,
        )
        if result.returncode != 0:
            sys.exit(f"ERROR: verify.py 실패")

    print()
    print(f"완료: {out}")


if __name__ == "__main__":
    main()
