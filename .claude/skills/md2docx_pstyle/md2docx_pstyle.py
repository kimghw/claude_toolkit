#!/usr/bin/env python3
"""
md2docx_pstyle — input(.docx) 의 줄 단위 스타일을 target.docx 어휘 기준으로 정규화

자체 변환 로직 없이 짝꿍 scan.py / apply.py 를 subprocess 로 호출한다.
scan 과 apply 사이에는 사용자 결정(AskUserQuestion) 이 필요해서 본 orchestrator
가 둘을 자동으로 묶지 않는다. 사용자/상위 에이전트가 명시적으로 subcommand 를
지정해 호출한다.

서브커맨드:
    scan   <input.docx> (--target <target.docx> | --reference <reference.docx>) [--out-report <json>]
        → scan.py 호출. JSON 보고서 생성. --target / --reference 는 mutually exclusive.
    apply  <input.docx> <decisions.json> [--out <patched.docx>]
        → apply.py 호출. docx patch.
"""

import os
import subprocess
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent
SCAN_SCRIPT  = SKILL_DIR / "scan.py"
APPLY_SCRIPT = SKILL_DIR / "apply.py"


def _subenv():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


HELP = """
md2docx_pstyle — input(.docx) 의 줄 단위 스타일을 target.docx 어휘 기준으로 정규화

서브커맨드
==========

  md2docx_pstyle help
      사용법 출력.

  md2docx_pstyle scan <input.docx> (--target <target.docx> | --reference <reference.docx>) [--out-report <json>]
      style source(target 또는 reference) 의 heading_inventory / list_styles /
      marker_hierarchy 와 input 의 pstyle_usage 를 추출해 JSON 보고서 생성.
      --target : 회사 양식 raw docx.
      --reference : target → reference 변환 산출물 docx (md2docx_target 의 출력).
      둘 다 styles.xml 동일 어휘로 추출 — mutually exclusive, 하나는 필수.
      기본 출력: cwd/md2docx_pstyle/<input_stem>_line.json   (단일 파일 — 재스캔 시 덮어쓰기)

  md2docx_pstyle apply <input.docx> <decisions.json> [--out <patched.docx>]
      decisions.json 의 매핑대로 input 의 pStyle / ind / numPr 정규화.
      기본: in-place. --out 지정 시 별도 파일.

작동 흐름
========

  [1] scan        → md2docx_pstyle/<input_stem>_line.json
  [2] (Claude 가 AskUserQuestion 으로 사용자 결정 받음)
                  → decisions.json 작성 (관행: md2docx_pstyle/<input_stem>_line_decisions.json)
  [3] apply       → 정규화된 docx

scan 과 apply 사이에 사용자 결정이 필요하므로 본 orchestrator 는 둘을
자동으로 묶지 않는다. (이전 md2docx_layout 의 scan_lists/apply_lists 흐름은
본 스킬로 통합되며 폐기.)

decisions.json action 종류
=========================

  rename          pStyle 만 target_style_id 로 교체. heading / standard /
                  styled 그룹에 사용.
  list_apply      pStyle 을 target list_style_id 로 + ind 설정 + (옵션)
                  numPr 제거. list / list_styled 그룹.
  marker_ind      pStyle 변경 없이 ind 만 target hierarchy 값으로 set.
                  marker 그룹 (마커 텍스트는 유지).
  marker_replace  numPr 제거 + (target ppr_inner 통째 복사 또는 ind 만
                  set) + 단락 앞에 마커 run 삽입. target marker_rpr 가
                  있으면 마커 run rPr 로 적용 (w:color 자동 제거). list
                  / list_styled / marker 를 target 양식의 marker 로
                  강제 교체할 때.
  skip            무변경.

자세한 필드는 SKILL.md 의 'decisions.json 스키마' 절 참조.

직접 호출도 가능:
  python scan.py  <input.docx> --target <target.docx>
  python scan.py  <input.docx> --reference <reference.docx>
  python apply.py <input.docx> <decisions.json>
"""


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    args = sys.argv[1:]
    if not args or args[0].lower() in ("help", "-h", "--help"):
        print(HELP)
        return 0

    sub = args[0]
    rest = args[1:]

    if sub == "scan":
        if not SCAN_SCRIPT.exists():
            print(f"ERROR: scan.py 없음: {SCAN_SCRIPT}", file=sys.stderr)
            return 1
        cmd = [sys.executable, str(SCAN_SCRIPT)] + rest
        sys.stdout.flush()
        return subprocess.run(cmd, env=_subenv()).returncode

    if sub == "apply":
        if not APPLY_SCRIPT.exists():
            print(f"ERROR: apply.py 없음: {APPLY_SCRIPT}", file=sys.stderr)
            return 1
        cmd = [sys.executable, str(APPLY_SCRIPT)] + rest
        sys.stdout.flush()
        return subprocess.run(cmd, env=_subenv()).returncode

    print(f"ERROR: 알 수 없는 서브커맨드: {sub!r}", file=sys.stderr)
    print(HELP, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
