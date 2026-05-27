#!/usr/bin/env python3
"""
md2docx_layout — pandoc 변환 후 output docx 의 표·페이지 후처리 orchestrator

서브 스크립트를 subprocess 로 호출:
    - postprocess_tables        : 표 디자인 (스타일 클론 + tblLook/cnfStyle + min-width + paragraph jc)
    - postprocess_table_spacing : 표 직후 단락 간격 (settings.json 기반)
    - postprocess_page          : 페이지 레이아웃 (pgSz/pgMar/cols/docGrid)
    - postprocess_header_footer : 머리글/바닥글 동기화 (--header-source 지정 시)

헤딩·리스트·마커 단락의 pStyle/ind 정규화는 별도 md2docx_pstyle 스킬 사용 —
이전 scan_lists.py/apply_lists.py 흐름은 md2docx_pstyle 으로 통합되며 폐기됐다.
사용자 결정(AskUserQuestion) 단계가 필요해 본 orchestrator 가 자동 호출하지 않는다.

입력은 보통 md2docx 가 만든 pandoc 출력:
    cwd/pandoc/<stem>_pandoc.docx
출력은:
    cwd/output/<stem>_output.docx     (stem 의 '_pandoc' 접미사 자동 제거)

reference 자동 탐색:
    .claude/skills/md2docx/template/*.docx 중 가장 최근 수정된 것 사용.
    없으면 페이지 동기화는 스킵, 표는 최소 patch 모드.

인자:
    md2docx_layout <input.docx>                              표+표간격+페이지 후처리
    md2docx_layout <input.docx> --reference <ref.docx>       reference 명시
    md2docx_layout <input.docx> --out <out.docx>             출력 경로 지정
    md2docx_layout <input.docx> --skip-tables                tables 단계 생략
    md2docx_layout <input.docx> --skip-table-spacing         표간격 단계 생략
    md2docx_layout <input.docx> --skip-page                  page 단계 생략
    md2docx_layout <input.docx> --settings <path.json>       settings.json 경로 (기본 skill 디렉토리)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent
TABLES_SCRIPT = SKILL_DIR / "postprocess_tables.py"
TBLSP_SCRIPT = SKILL_DIR / "postprocess_table_spacing.py"
PAGE_SCRIPT = SKILL_DIR / "postprocess_page.py"
HF_SCRIPT = SKILL_DIR / "postprocess_header_footer.py"

DEFAULT_SETTINGS_PATH = SKILL_DIR / "settings.json"
MD2DOCX_TEMPLATE_DIR = SKILL_DIR.parent / "md2docx" / "template"


HELP = """
md2docx_layout — pandoc 변환 후 docx 의 표·표간격·페이지·머리바닥 후처리 orchestrator

사용법:
    md2docx_layout help                                          사용법 출력
    md2docx_layout <input.docx>                                  표+표간격+페이지 후처리
    md2docx_layout <input.docx> --reference <ref.docx>           reference 명시 (페이지·표용)
    md2docx_layout <input.docx> --header-source <src.docx>       머리글/바닥글을 별도 docx 에서 복제
    md2docx_layout <input.docx> --settings <path.json>           settings.json 경로 (기본: skill/settings.json)
    md2docx_layout <input.docx> --out <out.docx>                 출력 경로 지정
    md2docx_layout <input.docx> --skip-tables                    tables 단계 생략
    md2docx_layout <input.docx> --skip-table-spacing             표간격 단계 생략
    md2docx_layout <input.docx> --skip-page                      page 단계 생략

기본 출력 경로:
    cwd/output/<stem>_output.docx
    (stem 이 '_pandoc' 으로 끝나면 그 접미사를 제거 후 '_output' 부착)

reference 자동 탐색 (페이지·표 용):
    .claude/skills/md2docx/template/*.docx 중 가장 최근 수정된 것.
    없으면 페이지 동기화는 스킵, 표는 최소 patch (tblLook/cnfStyle) 만.

표 직후 단락 간격 (post_table_spacing):
    settings.json 의 "post_table_spacing" 섹션 기반. 기본 mode='ensure' —
    표 직후 sibling 이 빈 단락이면 그 단락에 spacing 박고, 아니면 새 빈
    단락을 삽입한다. enabled=false 또는 mode='off' 면 단계 자체가 no-op.
    설정값은 twips 단위 (1pt=20twips, 240=12pt).

머리글/바닥글 동기화 (선택):
    --header-source 가 지정될 때만 실행. source docx 의 word/header*.xml,
    footer*.xml 중 텍스트가 있는 가장 풍부한 한 개씩 default 로 박는다.
    스타일·numbering 은 건드리지 않음. --reference 와 별개 인자 — 같은 파일을
    지정해도 되고 분리해도 됨.

예시:
    # 표준 흐름 (md2docx 가 만든 _pandoc.docx 를 입력)
    python md2docx_layout.py pandoc/report_pandoc.docx
    # → output/report_output.docx

    # reference 명시
    python md2docx_layout.py pandoc/report_pandoc.docx \\
        --reference .claude/skills/md2docx/template/company_ref.docx

    # 머리글/바닥글 까지 사용자 양식 원본에서 복제
    python md2docx_layout.py pandoc/report_pandoc.docx \\
        --reference .claude/skills/md2docx/template/company_ref.docx \\
        --header-source 408_Statement_HYSOL_Rev.00.docx

    # 표 간격만 끄고 싶을 때
    python md2docx_layout.py pandoc/report_pandoc.docx --skip-table-spacing

    # 사용자 별도 settings.json 사용
    python md2docx_layout.py pandoc/report_pandoc.docx --settings my_settings.json

    # page 단계만 (tables 생략)
    python md2docx_layout.py report.docx --skip-tables --skip-table-spacing
"""


def _subenv():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def pop_value(args: list[str], name: str) -> str | None:
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            sys.exit(f"ERROR: {name} 뒤에 값이 필요합니다.")
        val = args[i + 1]
        del args[i:i + 2]
        return val
    return None


def most_recent_cached_reference() -> Path | None:
    if not MD2DOCX_TEMPLATE_DIR.exists():
        return None
    cached = [p for p in MD2DOCX_TEMPLATE_DIR.glob("*.docx") if p.is_file()]
    if not cached:
        return None
    return max(cached, key=lambda p: p.stat().st_mtime)


def derive_output_path(input_path: Path) -> Path:
    stem = input_path.stem
    if stem.endswith("_pandoc"):
        stem = stem[: -len("_pandoc")]
    return Path.cwd() / "output" / f"{stem}_output.docx"


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

    reference_arg = pop_value(args, "--reference")
    header_source_arg = pop_value(args, "--header-source")
    settings_arg = pop_value(args, "--settings")
    out_arg = pop_value(args, "--out")
    flags = {a for a in args if a.startswith("--")}
    positional = [Path(a) for a in args if not a.startswith("--")]

    if len(positional) != 1:
        sys.exit(f"ERROR: input docx 는 정확히 하나 지정. 받은 것: {[str(p) for p in positional]}")

    inp = positional[0]
    if not inp.exists():
        sys.exit(f"ERROR: input 파일 없음: {inp}")
    if inp.suffix.lower() != ".docx":
        sys.exit(f"ERROR: input 은 .docx 여야 합니다: {inp}")

    skip_tables = "--skip-tables" in flags
    skip_tblsp = "--skip-table-spacing" in flags
    skip_page = "--skip-page" in flags
    if skip_tables and skip_tblsp and skip_page:
        sys.exit("ERROR: --skip-tables, --skip-table-spacing, --skip-page 모두 지정 — 할 일 없음.")

    settings_path: Path | None = None
    if settings_arg:
        settings_path = Path(settings_arg)
        if not settings_path.exists():
            sys.exit(f"ERROR: --settings 파일 없음: {settings_path}")
    elif DEFAULT_SETTINGS_PATH.exists():
        settings_path = DEFAULT_SETTINGS_PATH

    if not TABLES_SCRIPT.exists():
        sys.exit(f"ERROR: postprocess_tables 진입점 없음: {TABLES_SCRIPT}")
    if not TBLSP_SCRIPT.exists():
        sys.exit(f"ERROR: postprocess_table_spacing 진입점 없음: {TBLSP_SCRIPT}")
    if not PAGE_SCRIPT.exists():
        sys.exit(f"ERROR: postprocess_page 진입점 없음: {PAGE_SCRIPT}")
    if header_source_arg and not HF_SCRIPT.exists():
        sys.exit(f"ERROR: postprocess_header_footer 진입점 없음: {HF_SCRIPT}")

    # header_source 검증
    header_source: Path | None = None
    if header_source_arg:
        header_source = Path(header_source_arg)
        if not header_source.exists():
            sys.exit(f"ERROR: --header-source 파일 없음: {header_source}")
        if header_source.suffix.lower() != ".docx":
            sys.exit(f"ERROR: --header-source 는 .docx 여야 합니다: {header_source}")

    # reference 결정
    reference: Path | None = None
    if reference_arg:
        reference = Path(reference_arg)
        if not reference.exists():
            sys.exit(f"ERROR: reference 파일 없음: {reference}")
        print(f"[POST] reference (명시): {reference}")
    else:
        reference = most_recent_cached_reference()
        if reference is None:
            print(f"[POST] reference 자동 탐색 실패 ({MD2DOCX_TEMPLATE_DIR}) — 페이지 동기화 스킵, 표는 최소 patch")
        else:
            print(f"[POST] reference 자동: {reference}")

    output = Path(out_arg) if out_arg else derive_output_path(inp)
    output.parent.mkdir(parents=True, exist_ok=True)

    total_steps = 3 + (1 if header_source is not None else 0)

    # Step 1: tables — input → output (별도 경로) 으로 저장
    if not skip_tables:
        print()
        print(f"[1/{total_steps}] tables 후처리: {inp.name} -> {output.name}")
        cmd = [sys.executable, str(TABLES_SCRIPT), str(inp), "--out", str(output)]
        if reference is not None:
            cmd.extend(["--reference", str(reference)])
        sys.stdout.flush()
        r = subprocess.run(cmd, env=_subenv())
        if r.returncode != 0:
            sys.exit(f"ERROR: postprocess_tables 실패 (returncode={r.returncode})")
    else:
        print()
        print(f"[1/{total_steps}] tables 후처리: --skip-tables 로 생략, input 을 output 위치로 복사")
        if inp.resolve() != output.resolve():
            shutil.copy2(inp, output)

    # Step 2: table_spacing — output 에 in-place (settings.json 기반)
    if not skip_tblsp:
        print()
        print(f"[2/{total_steps}] table-spacing 후처리: {output.name} (in-place)")
        cmd = [sys.executable, str(TBLSP_SCRIPT), str(output)]
        if settings_path is not None:
            cmd.extend(["--settings", str(settings_path)])
        sys.stdout.flush()
        r = subprocess.run(cmd, env=_subenv())
        if r.returncode != 0:
            sys.exit(f"ERROR: postprocess_table_spacing 실패 (returncode={r.returncode})")
    else:
        print()
        print(f"[2/{total_steps}] table-spacing 후처리: --skip-table-spacing 로 생략")

    # Step 3: page — output 에 in-place
    if not skip_page:
        print()
        print(f"[3/{total_steps}] page 후처리: {output.name} (in-place)")
        cmd = [sys.executable, str(PAGE_SCRIPT), str(output)]
        if reference is not None:
            cmd.extend(["--reference", str(reference)])
        sys.stdout.flush()
        r = subprocess.run(cmd, env=_subenv())
        if r.returncode != 0:
            sys.exit(f"ERROR: postprocess_page 실패 (returncode={r.returncode})")
    else:
        print()
        print(f"[3/{total_steps}] page 후처리: --skip-page 로 생략")

    # Step 4: header/footer — --header-source 가 있을 때만
    if header_source is not None:
        print()
        print(f"[4/{total_steps}] header/footer 동기화: {output.name} ← {header_source.name} (in-place)")
        cmd = [sys.executable, str(HF_SCRIPT), str(output), "--source", str(header_source)]
        sys.stdout.flush()
        r = subprocess.run(cmd, env=_subenv())
        if r.returncode != 0:
            sys.exit(f"ERROR: postprocess_header_footer 실패 (returncode={r.returncode})")

    print()
    print(f"완료: {output}")
    print(f"      reference: {reference if reference is not None else '(없음)'}")
    if settings_path is not None:
        print(f"      settings:  {settings_path}")
    if header_source is not None:
        print(f"      header-source: {header_source}")


if __name__ == "__main__":
    main()
