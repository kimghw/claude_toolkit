#!/usr/bin/env python3
"""
md2docx_source — source(.md) 전처리 통합 진입점

파이프라인:
    source.md → [discover (옵션) + lint + strip] → source'.md (선택적)

인자 자동 분기:
    *.md                  → lint 검출, strip 검출
    *.md --discover       → 패턴 발견 (inventory + diff) 실행 후 종료
    *.md --skip-lint      → lint 단계 건너뛰기
    *.md --apply-strip    → 선택된 패턴 적용해 _prep.md 생성
    --verify              → 미지원 (convert 단계 없음)

내부적으로 discover.py(패턴 발견), lint.py(lint), strip.py(source 전처리)를 호출.
"""

import os
import subprocess
import sys
from pathlib import Path


def _subenv():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    return env


HELP = """
md2docx_source — source(.md) 전처리 파이프라인 (discover + lint + strip)

사용법
======

  python md2docx_source.py help                     사용법 출력
  python md2docx_source.py <source.md>              lint 검출, strip 패턴 검출
  python md2docx_source.py <source.md> --discover   inventory + diff 출력 후 종료
                                                    (LLM 이 새 패턴 제안 시 사용)
  python md2docx_source.py <source.md> --skip-lint  lint 건너뛰고 strip만 검출
  python md2docx_source.py <source.md> --apply-strip <pid1,pid2,...>
                                                    선택된 패턴 적용 → skill output/<source_stem>_prep.md
  python md2docx_source.py <source.md> --apply-strip <pid1,pid2,...> --out X.md
                                                    지정 경로로 저장

인자
====

  <source.md>           변환할 Markdown 입력(source).
                        산출물(<source>_prep.md) 은 스킬 내부 output/ 에 생성.
                        source 는 절대 수정되지 않는다.

  --discover            패턴 발견 단계만 실행 (lint·strip 건너뜀).
                        discover.py inventory + diff 를 순차 호출해
                        헤딩·번호 인벤토리와 카탈로그 미매칭 후보를 출력.
                        LLM 이 결과를 보고 strip_patterns.json 보강 여부를
                        판단할 때 사용. 카탈로그 등록은 discover.py add 직접 호출.

  --skip-lint           lint 단계 건너뛰기. 사용자가 모호한 넘버링/heading 을
                        이미 확인했거나 무시하기로 한 뒤 재실행할 때 사용.

  --apply-strip <pid1,pid2,...>
                        선택된 strip 패턴을 source.md (보존) 에 적용한 사본을
                        <skill_dir>/output/<source_stem>_prep.md 로 저장.

  --out <file>          --apply-strip 의 출력 경로 (선택).

예시
====

  # 넘버링/heading 검사 + 패턴 검출
  python md2docx_source.py report.md
      → [LINT-...] 및 [STRIP-MATCH] 출력, 필요시 재실행 가이드

  # lint 무시하고 strip 패턴 적용
  python md2docx_source.py report.md --apply-strip heading-manual-number,remove-hrule
      → <skill_dir>/output/report_prep.md 생성

  # 지정 경로로 저장
  python md2docx_source.py report.md --apply-strip p1,p2 --out custom.md
"""


def is_md(p: Path) -> bool:
    return p.suffix.lower() in (".md", ".markdown")


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

    positional = [Path(a) for a in args if not a.startswith("--")]

    md_files = [p for p in positional if is_md(p)]
    others = [p for p in positional if not is_md(p)]

    if others:
        sys.exit(f"ERROR: 지원하지 않는 확장자: {[str(p) for p in others]}\n`md2docx_source help` 참고.")
    if len(md_files) != 1:
        sys.exit(f"ERROR: source(.md) 는 정확히 하나 지정. 받은 것: {[str(p) for p in md_files]}")

    md = md_files[0]
    if not md.exists():
        sys.exit(f"ERROR: 파일 없음: {md}")

    here = Path(__file__).resolve().parent

    # === Step 0: discover (옵션) ===
    # `--discover` 가 있으면 inventory + diff 만 출력하고 종료한다.
    # LLM 이 결과를 보고 새 패턴을 strip_patterns.json 에 추가할지 판단한다.
    if "--discover" in flags:
        if apply_strip_ids:
            sys.exit("ERROR: --discover 는 --apply-strip 와 함께 쓸 수 없습니다.")
        print(f"[0/?] discover inventory: {md.name}")
        inv = subprocess.run(
            [sys.executable, str(here / "discover.py"), "inventory", str(md)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        if inv.stdout.strip():
            for line in inv.stdout.splitlines():
                print(f"      {line}")
        if inv.stderr.strip():
            print(inv.stderr, file=sys.stderr)
        if inv.returncode != 0:
            sys.exit(f"ERROR: discover.py inventory 실패 (returncode={inv.returncode})")
        print()
        print(f"[0/?] discover diff: {md.name}")
        diff = subprocess.run(
            [sys.executable, str(here / "discover.py"), "diff", str(md)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        if diff.stdout.strip():
            for line in diff.stdout.splitlines():
                print(f"      {line}")
        if diff.stderr.strip():
            print(diff.stderr, file=sys.stderr)
        if diff.returncode == 3:
            # 미매칭 후보 있음 — LLM 이 패턴 제안·검증·등록할 차례
            print()
            print("=" * 70)
            print("  카탈로그 미매칭 후보 발견 — LLM 패턴 제안 검토")
            print("=" * 70)
            print()
            print("  위 [DISCOVER-CANDIDATES] 줄들을 LLM 이 inventory 와 함께 보고:")
            print("    1) 추가 가치 있는 후보는 entry JSON 으로 작성")
            print("    2) python discover.py validate <entry.json> 로 검증")
            print("    3) python discover.py add <entry.json> 로 카탈로그 append")
            print("    4) 본 스크립트를 --discover 없이 재실행해 lint+strip 진행")
            print()
            sys.exit(3)
        elif diff.returncode != 0:
            sys.exit(f"ERROR: discover.py diff 실패 (returncode={diff.returncode})")
        print()
        print("완료: discover 단계 종료 (매칭 후보 없음). 이어서 lint+strip 을 진행하려면 --discover 없이 재실행.")
        return

    # === Step 1: Markdown lint (넘버링/heading 사전 검토) ===
    if "--skip-lint" not in flags and not apply_strip_ids:
        print(f"[1/?] Markdown lint: {md.name}")
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
            print("  위 [LINT-AMBIGUOUS] 항목을 확인해야 합니다.")
            print("  다음 중 하나로 처리하세요:")
            print()
            print("    1) source.md 파일을 수정해 모호성을 제거한 뒤 재실행")
            print("    2) 그대로 진행하려면 --skip-lint 추가해 재실행")
            print()
            sys.exit(2)
        elif lint_result.returncode != 0:
            print(f"      [LINT-WARN] lint.py returncode={lint_result.returncode} — 무시하고 진행")

    # === Step 2: strip — 패턴 검출 / 적용 (references/strip_patterns.json) ===
    if apply_strip_ids:
        # 선택된 패턴을 source 에 적용 → <skill_dir>/output/<source_stem>_prep.md 생성
        # (out_override 가 있으면 그 경로 사용; 없으면 strip.py 의 기본값 = skill output/)
        extra_args = ["--out", str(out_override)] if out_override else []
        target_label = str(out_override) if out_override else "(skill output/<stem>_prep.md)"
        print()
        print(f"[2/?] strip 적용: {md.name} -> {target_label}  (패턴: {', '.join(apply_strip_ids)})")
        strip_result = subprocess.run(
            [sys.executable, str(here / "strip.py"), str(md),
             "--apply", *apply_strip_ids, *extra_args],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=_subenv(),
        )
        for line in strip_result.stdout.splitlines():
            if line.startswith("[STRIP"):
                print(f"      {line}")
        if strip_result.returncode != 0:
            print(strip_result.stderr, file=sys.stderr)
            sys.exit(f"ERROR: strip.py --apply 실패 (returncode={strip_result.returncode})")
    else:
        # 패턴 검출만
        print()
        print(f"[2/?] strip 검출: {md.name}")
        strip_result = subprocess.run(
            [sys.executable, str(here / "strip.py"), str(md)],
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
            print("  원본 source.md 는 보존됩니다. 위 [STRIP-MATCH] 각 패턴에 대해")
            print("  선택 후:")
            print()
            print("    - 제거할 패턴 ID 들을 쉼표로 모아 다음 명령으로 재실행:")
            print(f"        python md2docx_source.py {md} --apply-strip <pid1>,<pid2>")
            print(f"      (원본 source 보존, <source_stem>_prep.md 생성)")
            print()
            print("    - 모두 유지: --skip-strip 대신 아무것도 하지 않으면 됩니다.")
            print()
            sys.exit(3)
        elif strip_result.returncode != 0:
            print(f"      [STRIP-WARN] strip.py returncode={strip_result.returncode} — 무시하고 진행")

    print()
    print(f"완료: {md.name} 전처리 완료")


if __name__ == "__main__":
    main()
