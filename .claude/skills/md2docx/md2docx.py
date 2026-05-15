#!/usr/bin/env python3
"""
md2docx — Markdown → DOCX 통합 진입점

인자 자동 분기:
    *.docx / *.doc                  → 매핑만, <원본명>_mapped.docx 저장
    *.md + *.docx                   → 매핑 + 변환, <원본md>.docx 저장
    --verify                        → 위 + XML/PDF 검증

내부적으로 map.py(매핑)와 verify.py(검증) + pandoc(변환)을 호출.
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
md2docx — Markdown을 회사 양식 docx로 변환하는 통합 파이프라인

사용법
======

  python md2docx.py help                         사용법 출력
  python md2docx.py <ref.docx>                   매핑만, <ref>_mapped.docx 저장
  python md2docx.py <input.md> <ref.docx>        매핑 + lint + md→docx 변환
  python md2docx.py <input.md> <ref.docx> --verify
                                                  위 + XML/PDF 검증

인자
====

  <ref.docx>     회사 reference Word 템플릿 (.docx 또는 .dotx)
                 매핑 적용 결과는 같은 폴더에 <원본명>_mapped.docx 로 저장.

  <input.md>     변환할 Markdown 파일.
                 변환 결과는 <input>.docx 로 저장 (같은 폴더).

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

예시
====

  # 새 회사 양식 받았을 때 — 매핑만
  python md2docx.py company.docx
      → company_mapped.docx 생성 (Pandoc reference로 사용 가능)

  # 일상 변환 — md를 회사 양식으로
  python md2docx.py report.md company.docx
      → report.docx 생성 (회사 양식 적용)

  # 변환 + 시각 검증
  python md2docx.py report.md company.docx --verify

  # 한 번 매핑하고 일상은 mapped만 재사용 (반복 변환 시 효율적)
  python md2docx.py company.docx               # 1회만
  python md2docx.py report.md company_mapped.docx  # 매번
"""


def is_docx(p: Path) -> bool:
    return p.suffix.lower() in (".docx", ".dotx", ".doc")


def is_md(p: Path) -> bool:
    return p.suffix.lower() in (".md", ".markdown")


def get_mapped_path(ref: Path) -> Path:
    """원본 옆에 <원본명>_mapped.docx 경로 생성. 이미 _mapped면 그대로 사용."""
    if ref.stem.endswith("_mapped"):
        return ref
    return ref.with_name(ref.stem + "_mapped.docx")


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

    docx_files = [p for p in positional if is_docx(p)]
    md_files = [p for p in positional if is_md(p)]
    others = [p for p in positional if not (is_docx(p) or is_md(p))]

    if others:
        sys.exit(f"ERROR: 지원하지 않는 확장자: {[str(p) for p in others]}\n`md2docx help` 참고.")
    if not docx_files:
        sys.exit("ERROR: reference.docx 인자가 필요합니다.\n`md2docx help` 참고.")
    if len(docx_files) > 1:
        sys.exit(f"ERROR: reference.docx는 하나만 지정. 받은 것: {[str(p) for p in docx_files]}")
    if len(md_files) > 1:
        sys.exit(f"ERROR: markdown 파일은 하나만 지정. 받은 것: {[str(p) for p in md_files]}")

    ref = docx_files[0]
    if not ref.exists():
        sys.exit(f"ERROR: 파일 없음: {ref}")

    here = Path(__file__).resolve().parent
    mapped = get_mapped_path(ref)

    # === Step 1: 매핑 ===
    if mapped == ref:
        print(f"[1/?] 이미 매핑된 파일로 보임 (이름에 _mapped 포함): {ref}")
        print(f"      매핑 단계 건너뜀.")
    else:
        print(f"[1/?] 매핑 적용: {ref.name} -> {mapped.name}")
        # 리포트는 파일로 저장 — stdout 인코딩 이슈 회피
        report_path = mapped.parent / "_mapping-report.md"
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
        # 선택된 패턴을 원본에 적용 → <stem>_stripped.md 생성, 변환 입력으로 사용
        stripped = md.with_name(md.stem + "_stripped" + md.suffix) if not md.stem.endswith("_stripped") else md
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
    # 출력 docx 이름은 (1) --out 지정, (2) 없으면 원본 .md stem 기준 (stripped 사본 stem 아님)
    out = out_override if out_override else original_md.with_suffix(".docx")
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

    # === Step 3: verify (옵션) ===
    if "--verify" in flags:
        verify_dir = md.parent / "verify_out"
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
