#!/usr/bin/env python3
"""
md2docx/postprocess_page.py — pandoc 변환 후 docx 의 페이지 레이아웃 동기화

문제:
    pandoc 은 보통 reference 의 sectPr 를 그대로 사용하지만, 사용자가
    reference 를 교체하거나 별도 sectPr 가 끼어들면 페이지 여백이 어긋날 수
    있다.

해결:
    reference docx 의 마지막 sectPr 에서 <w:pgSz>, <w:pgMar>, <w:cols>,
    <w:docGrid> 를 추출해 대상 docx 의 모든 sectPr 에 덮어쓴다. 이로써 회사
    양식의 페이지 여백/용지 크기를 보장한다.

Usage:
    python postprocess_page.py <docx>                          # reference 자동 탐색
    python postprocess_page.py <docx> --reference <ref.docx>   # 명시
    python postprocess_page.py <docx> --out <new.docx>
    python postprocess_page.py <docx> --dry-run                # 추출 정보만

종료 코드:
    0 = 성공 (reference/sectPr 없어 스킵 포함)
    1 = 실행 오류
"""

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


# 페이지 레이아웃 (section properties) 동기화용
SECTPR_RE           = re.compile(r'<w:sectPr\b[^>]*>.*?</w:sectPr>', re.DOTALL)
SECTPR_SELFCLOSE_RE = re.compile(r'<w:sectPr\b[^/]*/>')
PGSZ_RE             = re.compile(r'<w:pgSz\b[^/]*/>')
PGMAR_RE            = re.compile(r'<w:pgMar\b[^/]*/>')
COLS_RE             = re.compile(r'<w:cols\b[^/]*/>')
DOCGRID_RE          = re.compile(r'<w:docGrid\b[^/]*/>')


def extract_page_settings(doc_xml: str) -> dict:
    """document.xml 에서 마지막 sectPr 의 페이지 레이아웃 요소들을 추출.
    Word 문서의 권위 있는 페이지 설정은 보통 body 끝의 마지막 sectPr 이다.
    Returns: {'pgSz': '<w:pgSz .../>', 'pgMar': '<w:pgMar .../>', 'cols': ..., 'docGrid': ...}
    누락된 요소는 dict 에 키가 없음."""
    sects = SECTPR_RE.findall(doc_xml)
    if not sects:
        return {}
    last = sects[-1]
    out = {}
    for key, pat in (('pgSz', PGSZ_RE), ('pgMar', PGMAR_RE),
                     ('cols', COLS_RE), ('docGrid', DOCGRID_RE)):
        m = pat.search(last)
        if m:
            out[key] = m.group(0)
    return out


def apply_page_settings(doc_xml: str, settings: dict) -> tuple:
    """모든 <w:sectPr> 의 pgSz/pgMar/cols/docGrid 요소를 settings 의 값으로 교체.
    sectPr 내에 해당 요소가 없으면 추가. self-closing sectPr 는 건드리지 않음
    (continuous section 등 — 페이지 레이아웃이 적용되지 않는 경우).

    Returns: (new_doc_xml, n_sects_patched)
    """
    if not settings:
        return doc_xml, 0

    patched_count = 0

    def patch_one_sect(m):
        nonlocal patched_count
        sect = m.group(0)
        patched_count += 1
        new_sect = sect
        # 각 요소를 교체 또는 추가
        for key, pat in (('pgSz', PGSZ_RE), ('pgMar', PGMAR_RE),
                         ('cols', COLS_RE), ('docGrid', DOCGRID_RE)):
            if key not in settings:
                continue
            new_el = settings[key]
            if pat.search(new_sect):
                new_sect = pat.sub(new_el, new_sect, count=1)
            else:
                # </w:sectPr> 직전에 추가
                new_sect = new_sect.replace('</w:sectPr>', new_el + '</w:sectPr>', 1)
        return new_sect

    new_doc = SECTPR_RE.sub(patch_one_sect, doc_xml)
    return new_doc, patched_count


def postprocess(docx_in: Path, docx_out: Path,
                reference: Path = None) -> dict:
    """Returns: {'sections_patched': N, 'elements': [...], 'status': 'ok'|'no-reference'|'no-sectpr'}

    reference 의 pgSz/pgMar/cols/docGrid 를 모든 sectPr 에 덮어써 페이지 여백을
    reference 와 동일하게 보장.
    """
    # reference 가 없으면 스킵
    if reference is None or not reference.exists():
        # 입력=출력 이 다르면 그래도 복사
        if docx_in.resolve() != docx_out.resolve():
            shutil.copyfile(str(docx_in), str(docx_out))
        return {'sections_patched': 0, 'elements': [], 'status': 'no-reference'}

    # reference 에서 페이지 설정 추출
    try:
        with zipfile.ZipFile(reference) as zref:
            ref_doc_xml = zref.read('word/document.xml').decode('utf-8')
    except (KeyError, FileNotFoundError):
        if docx_in.resolve() != docx_out.resolve():
            shutil.copyfile(str(docx_in), str(docx_out))
        return {'sections_patched': 0, 'elements': [], 'status': 'no-reference'}

    settings = extract_page_settings(ref_doc_xml)
    if not settings:
        if docx_in.resolve() != docx_out.resolve():
            shutil.copyfile(str(docx_in), str(docx_out))
        return {'sections_patched': 0, 'elements': [], 'status': 'no-sectpr'}

    # 대상 docx 의 document.xml 패치
    with zipfile.ZipFile(docx_in) as zin:
        names = zin.namelist()
        contents = {n: zin.read(n) for n in names}

    doc_xml = contents['word/document.xml'].decode('utf-8')
    new_doc, n_sects = apply_page_settings(doc_xml, settings)
    contents['word/document.xml'] = new_doc.encode('utf-8')

    with zipfile.ZipFile(docx_out, 'w', zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, contents[name])

    return {
        'sections_patched': n_sects,
        'elements': sorted(settings.keys()),
        'status': 'ok',
    }


def main():
    ap = argparse.ArgumentParser(description="pandoc 변환 후 docx 의 페이지 레이아웃 동기화")
    ap.add_argument('docx', help="대상 docx (in-place 또는 --out 지정)")
    ap.add_argument('--reference', help="회사 reference docx (페이지 설정 소스)")
    ap.add_argument('--out', help="별도 출력 경로 (기본: in-place)")
    ap.add_argument('--dry-run', action='store_true',
                    help="패치 안 하고 reference 에서 추출 가능한 요소만 보고")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

    inp = Path(args.docx)
    if not inp.exists():
        print(f"ERROR: not found: {inp}", file=sys.stderr)
        return 1

    # reference 결정: --reference 우선, 아니면 스킬 references/ 하위 자동 탐색
    ref_path = None
    if args.reference:
        ref_path = Path(args.reference)
    else:
        here = Path(__file__).resolve().parent
        for cand in (here / "template" / "reference_reg_mapped.docx",
                     here / "references" / "reference_reg_mapped.docx",
                     here / "references" / "reference_reg.docx"):
            if cand.exists():
                ref_path = cand
                break
    if ref_path is not None and not ref_path.exists():
        print(f"      [POSTPROCESS-PAGE-WARN] reference 없음 ({ref_path}) — 동기화 건너뜀")
        ref_path = None

    if args.dry_run:
        if ref_path is None:
            print(f"[POSTPROCESS-PAGE-DRY] reference 없음 — 추출 불가")
            return 0
        try:
            with zipfile.ZipFile(ref_path) as z:
                ref_doc_xml = z.read('word/document.xml').decode('utf-8')
        except (KeyError, FileNotFoundError):
            print(f"[POSTPROCESS-PAGE-DRY] reference document.xml 읽기 실패")
            return 0
        settings = extract_page_settings(ref_doc_xml)
        if not settings:
            print(f"[POSTPROCESS-PAGE-DRY] reference 에 sectPr 가 없거나 페이지 요소 없음")
            return 0
        els = ', '.join(sorted(settings.keys()))
        print(f"[POSTPROCESS-PAGE-DRY] {ref_path.name} 에서 추출 가능: {els}")
        return 0

    out = Path(args.out) if args.out else inp

    def do(in_path, out_path):
        return postprocess(in_path, out_path, reference=ref_path)

    if out.resolve() == inp.resolve():
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            info = do(inp, tmp_path)
            shutil.move(str(tmp_path), str(inp))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        loc = "in-place"
    else:
        info = do(inp, out)
        loc = str(out.name)

    if info['status'] == 'ok':
        els = ', '.join(info['elements'])
        print(f"[POSTPROCESS-PAGE] reference 의 페이지 설정({els})을 {info['sections_patched']}개 sectPr 에 동기화 ({loc})")
    elif info['status'] == 'no-reference':
        print(f"[POSTPROCESS-PAGE] reference 없음 — 동기화 건너뜀 ({loc})")
    elif info['status'] == 'no-sectpr':
        print(f"[POSTPROCESS-PAGE] reference 페이지 설정 추출 실패 — 동기화 건너뜀 ({loc})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
