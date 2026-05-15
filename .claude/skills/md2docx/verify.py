#!/usr/bin/env python3
"""
md2doc_style_matching/verify.py

매핑된 reference.docx의 효과를 end-to-end로 검증한다.

작동:
  1. 동일 md를 두 번 변환 — (a) 매핑 없이 (b) 매핑 적용
  2. XML 레벨 검증 — 출력 docx의 모든 스타일 참조가 해소되는지 확인
  3. PDF 추출 — 시각 비교용 (docx2pdf 필요, Windows + MS Word)

Usage:
    python verify.py <input.md> --mapped-ref <reference_mapped.docx>
    python verify.py <input.md> --mapped-ref ... --out-dir verify_out
    python verify.py <input.md> --mapped-ref ... --no-pdf       # PDF 생략
"""

import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path


def run(cmd):
    print(f"$ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True)


def convert_md(md_path, output_docx, reference_doc=None):
    cmd = ["pandoc", str(md_path), "-o", str(output_docx)]
    if reference_doc:
        cmd.append(f"--reference-doc={reference_doc}")
    run(cmd)


def verify_xml(docx_path):
    """document.xml의 모든 스타일 참조가 styles.xml에 정의돼 있는지."""
    with zipfile.ZipFile(docx_path) as z:
        doc = z.read("word/document.xml").decode("utf-8")
        sty = z.read("word/styles.xml").decode("utf-8")

    defined = set(re.findall(r'w:styleId="([^"]+)"', sty))
    name_map = {}
    for m in re.finditer(r'<w:style[^>]*w:styleId="([^"]+)"[^>]*>(.*?)</w:style>', sty, re.DOTALL):
        sid, body = m.group(1), m.group(2)
        name_m = re.search(r'<w:name\s+w:val="([^"]+)"', body)
        name_map[sid] = name_m.group(1) if name_m else "(no name)"

    refs = re.findall(r'<w:(?:pStyle|rStyle|tblStyle)\s+w:val="([^"]+)"', doc)
    ok, missing = [], []
    for r in sorted(set(refs)):
        cnt = refs.count(r)
        if r in defined:
            ok.append((r, name_map.get(r, "?"), cnt))
        else:
            missing.append((r, cnt))
    return {"ok": ok, "missing": missing}


def convert_pdf(docx_path, pdf_path):
    try:
        from docx2pdf import convert
    except ImportError:
        print("  ERROR: docx2pdf 미설치. `pip install docx2pdf` 후 재시도.")
        return False
    try:
        convert(str(docx_path), str(pdf_path))
        return Path(pdf_path).exists()
    except Exception as e:
        print(f"  ERROR: PDF 변환 실패: {e}")
        return False


def print_xml_report(label, docx_path, result):
    print(f"\n  [{label}] {Path(docx_path).name}")
    print(f"  OK: {len(result['ok'])} 스타일 참조 해소")
    for sid, name, cnt in result["ok"]:
        print(f"    {sid:25} x{cnt:3} -> {name}")
    if result["missing"]:
        print(f"  MISSING (Normal로 폴백): {len(result['missing'])}")
        for sid, cnt in result["missing"]:
            print(f"    {sid:25} x{cnt}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    p = argparse.ArgumentParser(description="매핑 적용 검증 — XML + PDF 비교")
    p.add_argument("md", help="입력 markdown 파일")
    p.add_argument("--mapped-ref", required=True, help="매핑된 reference.docx")
    p.add_argument("--out-dir", default=".", help="검증 산출물 디렉토리 (기본: 현재)")
    p.add_argument("--no-pdf", action="store_true", help="PDF 변환 생략 (XML 검증만)")
    args = p.parse_args()

    md = Path(args.md)
    mapped_ref = Path(args.mapped_ref)
    if not md.exists():
        sys.exit(f"ERROR: not found: {md}")
    if not mapped_ref.exists():
        sys.exit(f"ERROR: not found: {mapped_ref}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    no_map_docx = out_dir / "verify_no_mapping.docx"
    mapped_docx = out_dir / "verify_mapped.docx"

    print("=" * 60)
    print("[1/3] 두 가지 변환")
    print("=" * 60)
    convert_md(md, no_map_docx, None)
    convert_md(md, mapped_docx, mapped_ref)

    print()
    print("=" * 60)
    print("[2/3] XML 레벨 검증")
    print("=" * 60)
    r_no = verify_xml(no_map_docx)
    r_mp = verify_xml(mapped_docx)
    print_xml_report("매핑 없음", no_map_docx, r_no)
    print_xml_report("매핑 적용", mapped_docx, r_mp)

    improved = len(r_no["missing"]) - len(r_mp["missing"])
    print()
    print(f"  >>> 매핑 효과: missing {len(r_no['missing'])} -> {len(r_mp['missing'])} ({'+' if improved >= 0 else ''}{improved} 개선)")

    if not args.no_pdf:
        print()
        print("=" * 60)
        print("[3/3] PDF 추출 (시각 비교용)")
        print("=" * 60)
        pdf_paths = []
        for dx in [no_map_docx, mapped_docx]:
            pdf = dx.with_suffix(".pdf")
            print(f"\n  {dx.name} -> {pdf.name}")
            if convert_pdf(dx, pdf):
                print(f"  OK ({pdf.stat().st_size} bytes)")
                pdf_paths.append(pdf)
            else:
                print(f"  FAIL")
        if len(pdf_paths) == 2:
            print()
            print(f"  → 두 PDF 시각 비교:")
            print(f"    {pdf_paths[0]}  (Pandoc 기본 스타일)")
            print(f"    {pdf_paths[1]}  (회사 양식 적용)")
            print(f"  확인 포인트: 헤딩 번호 매김, 표 색상/테두리, 인용 스타일, 인라인 코드/링크")


if __name__ == "__main__":
    main()
