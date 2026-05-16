#!/usr/bin/env python3
"""
md2docx/postprocess_tables.py — pandoc 변환 후 docx 의 표 디자인 적용

문제:
    pandoc 출력 docx 의 표는 `<w:tblStyle w:val="Table"/>` 를 참조하고
    `Table` 스타일은 회사 `Table Grid` (aa) 를 basedOn 한다. 그러나 Word 는
    table 스타일의 `tblBorders` 와 `tblStylePr` (firstRow/firstCol conditional)
    를 basedOn 만으로 완전히 propagate 하지 않는다. 결과적으로 변환 docx 의
    표는 가는 회색 테두리 + conditional 채움 비활성 상태가 된다.

해결:
    reference 의 Table Grid 스타일 정의 전체를 변환 docx 의 `Table` 스타일에
    **deep copy** (name 은 'Table' 유지). basedOn 의존 없이 모든 속성
    (tblBorders, tblStylePr firstRow/firstCol, pPr, rPr) 이 로컬에 박힌다.

추가 패치 (조건 부수적):
    1) <w:tblPr> 의 <w:tblLook> 를 reference 와 동일 (04A0: firstRow=1,
       firstColumn=1, noVBand=1) 로 교체 → conditional 트리거 활성화.
    2) 위치별 cnfStyle 을 셀 tcPr 과 단락 pPr 양쪽에 박음:
         - 코너(r=0,c=0): firstColumn
         - 첫 행 본문(r=0,c>0): firstRow
         - 첫 열 본문(r>0,c=0): firstColumn
         - 일반 본문: 모든 비트 0
    3) 표 셀 단락의 pStyle="Compact" 제거.

Usage:
    python postprocess_tables.py <docx>                          # reference 자동 탐색
    python postprocess_tables.py <docx> --reference <ref.docx>   # 명시
    python postprocess_tables.py <docx> --no-style-clone         # 스타일 클론 생략
    python postprocess_tables.py <docx> --out <new.docx>
    python postprocess_tables.py <docx> --dry-run                # 표 개수만

종료 코드:
    0 = 성공
    1 = 실행 오류
"""

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


# 회사 reference 표의 tblLook — firstRow + firstColumn + noVBand
REF_TBLLOOK = (
    '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" '
    'w:firstColumn="1" w:lastColumn="0" w:noHBand="0" w:noVBand="1"/>'
)

# cnfStyle 비트맵: firstRow(0), lastRow(1), firstColumn(2), lastColumn(3),
#                   oddVBand(4), evenVBand(5), oddHBand(6), evenHBand(7),
#                   firstRowFirstColumn(8), firstRowLastColumn(9),
#                   lastRowFirstColumn(10), lastRowLastColumn(11)
def cnf(first_row=0, first_col=0, fr_fc=0):
    bits = ['0'] * 12
    if first_row: bits[0] = '1'
    if first_col: bits[2] = '1'
    if fr_fc:     bits[8] = '1'
    val = ''.join(bits)
    return (
        f'<w:cnfStyle w:val="{val}" '
        f'w:firstRow="{first_row}" w:lastRow="0" '
        f'w:firstColumn="{first_col}" w:lastColumn="0" '
        f'w:oddVBand="0" w:evenVBand="0" w:oddHBand="0" w:evenHBand="0" '
        f'w:firstRowFirstColumn="{fr_fc}" w:firstRowLastColumn="0" '
        f'w:lastRowFirstColumn="0" w:lastRowLastColumn="0"/>'
    )

CNF_FIRSTROW         = cnf(first_row=1)
CNF_FIRSTCOL         = cnf(first_col=1)
CNF_FIRSTROW_FIRSTCOL = cnf(first_row=1, first_col=1, fr_fc=1)
CNF_NORMAL           = cnf()  # 모든 비트 0 — 정상 셀 (reference 가 본문 셀에 박는 패턴)


TBL_RE              = re.compile(r'<w:tbl(?:\s[^>]*)?>.*?</w:tbl>', re.DOTALL)
TR_RE               = re.compile(r'<w:tr(?:\s[^>]*)?>.*?</w:tr>', re.DOTALL)
TC_RE               = re.compile(r'<w:tc>.*?</w:tc>', re.DOTALL)
TBLPR_RE            = re.compile(r'<w:tblPr>(.*?)</w:tblPr>', re.DOTALL)
TBLGRID_RE          = re.compile(r'<w:tblGrid>(.*?)</w:tblGrid>', re.DOTALL)
TBLLOOK_RE          = re.compile(r'<w:tblLook(?:\s[^/]*)?/>', re.DOTALL)
GRIDCOL_RE          = re.compile(r'<w:gridCol\s+w:w="(\d+)"\s*/>')
TCW_RE              = re.compile(r'<w:tcW\s+([^/]*?)/>')
TCPR_SELFCLOSE_RE   = re.compile(r'<w:tcPr\s*/>')
TCPR_OPEN_RE        = re.compile(r'<w:tcPr>')
PPR_SELFCLOSE_RE    = re.compile(r'<w:pPr\s*/>')
PPR_OPEN_RE         = re.compile(r'<w:pPr>')
P_RE                = re.compile(r'(<w:p\b[^>]*>)(.*?)</w:p>', re.DOTALL)
COMPACT_RE          = re.compile(r'<w:pStyle\s+w:val="Compact"\s*/>')

# 너비 단위: docx 는 twentieths of a point (= 1/1440 inch).
# 1 cm = 1/2.54 inch = 1/2.54 * 1440 twips ≈ 566.93 → 567 로 반올림.
TWIPS_PER_CM = 567
MIN_COL_TWIPS_DEFAULT = TWIPS_PER_CM  # 1cm


def patch_tblpr_look(tbl_xml: str) -> str:
    """이 표의 <w:tblPr> 안 <w:tblLook> 을 REF_TBLLOOK 로 교체. 없으면 추가."""
    def repl(m):
        inner = m.group(1)
        if TBLLOOK_RE.search(inner):
            new_inner = TBLLOOK_RE.sub(REF_TBLLOOK, inner, count=1)
        else:
            new_inner = inner + REF_TBLLOOK
        return f'<w:tblPr>{new_inner}</w:tblPr>'
    return TBLPR_RE.sub(repl, tbl_xml, count=1)


def replace_tblpr_with_reference_pattern(tbl_xml: str, ref_tblpr_inner: str) -> str:
    """pandoc 이 박은 tblPr 속성(tblLayout fixed, tblW pct 등) 을 버리고,
    reference 표의 tblPr 패턴 (tblStyle, tblW auto, tblLook 04A0) 으로 통째 교체.

    이렇게 하면 reference 의 table 스타일(이미 클론됨) 의 tblBorders / tblStylePr 가
    어떤 inline override 도 없이 그대로 렌더된다."""
    return TBLPR_RE.sub(f'<w:tblPr>{ref_tblpr_inner}</w:tblPr>', tbl_xml, count=1)


def extract_reference_tblpr(ref_doc_xml: str):
    """reference docx 의 document.xml 에서 첫 표의 <w:tblPr> 내부 추출.
    실제 reference 가 표에 박는 패턴 그대로 가져옴 (tblStyle/tblW/tblLook 등)."""
    tbl_m = TBL_RE.search(ref_doc_xml)
    if not tbl_m:
        return None
    pr_m = TBLPR_RE.search(tbl_m.group(0))
    return pr_m.group(1) if pr_m else None


def adjust_tblpr_for_target(ref_tblpr_inner: str, target_style_id: str) -> str:
    """reference 의 tblPr 패턴에서 tblStyle 값을 target_style_id 로 교체."""
    return re.sub(
        r'<w:tblStyle\s+w:val="[^"]+"\s*/>',
        f'<w:tblStyle w:val="{target_style_id}"/>',
        ref_tblpr_inner, count=1,
    )


def extract_style_tblborders(ref_styles_xml: str, style_name: str = "Table Grid"):
    """reference 의 <style_name> 스타일의 tblPr 안 <w:tblBorders> 블록을 그대로 반환.
    Word 가 클론된 스타일의 tblBorders 를 inheritance 로 honor 하지 않을 때를 대비해
    표 tblPr 에 inline 으로 박기 위함."""
    _, body = find_style_id_by_name(ref_styles_xml, style_name)
    if not body:
        return None
    pr_m = re.search(r'<w:tblPr>(.*?)</w:tblPr>', body, re.DOTALL)
    if not pr_m:
        return None
    bm = re.search(r'<w:tblBorders>.*?</w:tblBorders>', pr_m.group(1), re.DOTALL)
    return bm.group(0) if bm else None


def inline_inject_borders_in_tblpr(tblpr_inner: str, borders_xml: str) -> str:
    """tblPr 패턴 안에 tblBorders 를 inline 삽입.
    Schema 순서: tblStyle → tblW → tblBorders → tblLayout → tblCellMar → tblLook.
    tblLook 앞에 삽입하면 안전."""
    if not borders_xml or '<w:tblBorders' in tblpr_inner:
        return tblpr_inner
    look_m = TBLLOOK_RE.search(tblpr_inner)
    if look_m:
        return tblpr_inner[:look_m.start()] + borders_xml + tblpr_inner[look_m.start():]
    return tblpr_inner + borders_xml


def inject_cnfstyle(tc_xml: str, cnf_xml: str) -> str:
    """셀 XML 의 tcPr 안 맨 앞에 cnfStyle 삽입.
    self-closing <w:tcPr/>, 일반 <w:tcPr>...</w:tcPr>, 없음 세 경우 모두 처리."""
    m = TCPR_SELFCLOSE_RE.search(tc_xml)
    if m:
        return tc_xml.replace(m.group(0), f'<w:tcPr>{cnf_xml}</w:tcPr>', 1)
    if TCPR_OPEN_RE.search(tc_xml):
        return TCPR_OPEN_RE.sub(f'<w:tcPr>{cnf_xml}', tc_xml, count=1)
    return tc_xml.replace('<w:tc>', f'<w:tc><w:tcPr>{cnf_xml}</w:tcPr>', 1)


def inject_cnfstyle_in_paragraphs(tc_xml: str, cnf_xml: str) -> str:
    """셀 안 모든 <w:p> 의 pPr 에 cnfStyle 삽입.
    reference 표는 셀 tcPr 뿐 아니라 단락 pPr 에도 같은 cnfStyle 을 박는다 —
    Word 가 tblStylePr 의 글자 conditional (bold, color, fill 등) 을 단락 단위로
    적용하기 위함."""
    def patch_p(m):
        open_tag = m.group(1)
        body = m.group(2)
        # pPr self-closing
        sm = PPR_SELFCLOSE_RE.search(body)
        if sm:
            new_body = body.replace(sm.group(0), f'<w:pPr>{cnf_xml}</w:pPr>', 1)
        elif PPR_OPEN_RE.search(body):
            new_body = PPR_OPEN_RE.sub(f'<w:pPr>{cnf_xml}', body, count=1)
        else:
            new_body = f'<w:pPr>{cnf_xml}</w:pPr>' + body
        return f'{open_tag}{new_body}</w:p>'
    return P_RE.sub(patch_p, tc_xml)


def patch_cell(tc_xml: str, cnf_xml: str) -> str:
    """셀 tcPr 에 cnfStyle 박고, 단락 pPr 에도 동일 cnfStyle 박음."""
    tc_xml = inject_cnfstyle(tc_xml, cnf_xml)
    tc_xml = inject_cnfstyle_in_paragraphs(tc_xml, cnf_xml)
    return tc_xml


def patch_table_cnfstyle(tbl_xml: str) -> str:
    """모든 셀의 위치에 따라 cnfStyle 부여. reference 패턴 모방:
        - 코너 (r=0, c=0):  firstColumn (firstRow=0) — 헤더 주황 제외, 첫 열 강조만
        - 첫 행 본문 (r=0, c>0):  firstRow
        - 첫 열 본문 (r>0, c=0):  firstColumn
        - 일반 본문 (r>0, c>0):   모든 비트 0 (정상)
    tcPr 와 단락 pPr 양쪽에 동일 cnfStyle 박는다."""
    trs = list(TR_RE.finditer(tbl_xml))
    if not trs:
        return tbl_xml

    new_tbl = tbl_xml
    # 뒤에서부터 치환 (앞 인덱스 보존)
    for ri in range(len(trs) - 1, -1, -1):
        tr_m = trs[ri]
        tr = tr_m.group(0)
        tcs = list(TC_RE.finditer(tr))
        if not tcs:
            continue

        new_tr = tr
        for ci in range(len(tcs) - 1, -1, -1):
            tc_m = tcs[ci]
            if ri == 0 and ci == 0:
                cnf_xml = CNF_FIRSTCOL          # 코너 = 첫 열만
            elif ri == 0:
                cnf_xml = CNF_FIRSTROW          # 헤더 행 본문
            elif ci == 0:
                cnf_xml = CNF_FIRSTCOL          # 첫 열 본문
            else:
                cnf_xml = CNF_NORMAL            # 일반 본문 셀
            new_tc = patch_cell(tc_m.group(0), cnf_xml)
            new_tr = new_tr[:tc_m.start()] + new_tc + new_tr[tc_m.end():]

        new_tbl = new_tbl[:tr_m.start()] + new_tr + new_tbl[tr_m.end():]
    return new_tbl


def remove_compact_in_tables(tbl_xml: str) -> str:
    """표 안 단락의 pStyle='Compact' 제거 (회사 Normal 상속하도록)."""
    return COMPACT_RE.sub('', tbl_xml)


def enforce_min_col_width(tbl_xml: str, min_twips: int = MIN_COL_TWIPS_DEFAULT) -> str:
    """tblGrid 의 gridCol 너비와 셀의 tcW(dxa) 너비를 모두 min_twips 이상으로 강제.
    docx 너비 단위는 twips (1/1440 inch); 1cm ≈ 567 twips."""
    if min_twips <= 0:
        return tbl_xml

    # 1) tblGrid: <w:gridCol w:w="N"/>
    def patch_gridcol(m):
        w = int(m.group(1))
        new_w = max(w, min_twips)
        return f'<w:gridCol w:w="{new_w}"/>'
    new_tbl = GRIDCOL_RE.sub(patch_gridcol, tbl_xml)

    # 2) 각 셀의 tcW: <w:tcW w:w="N" w:type="dxa"/> (또는 attribute 순서 다를 수 있음)
    def patch_tcw(m):
        attrs = m.group(1)
        type_m = re.search(r'w:type="([^"]+)"', attrs)
        if not type_m or type_m.group(1) != 'dxa':
            return m.group(0)
        w_m = re.search(r'w:w="(\d+)"', attrs)
        if not w_m:
            return m.group(0)
        w = int(w_m.group(1))
        if w >= min_twips:
            return m.group(0)
        new_attrs = re.sub(r'w:w="\d+"', f'w:w="{min_twips}"', attrs, count=1)
        return f'<w:tcW {new_attrs}/>'
    new_tbl = TCW_RE.sub(patch_tcw, new_tbl)
    return new_tbl


# ---------------------------------------------------------------------------
# 스타일 클론: reference 의 Table Grid → 변환 docx 의 Table 스타일
# ---------------------------------------------------------------------------

def find_style_id_by_name(styles_xml: str, target_name: str):
    """w:name 이 target_name 인 스타일의 (styleId, body) 반환. 없으면 (None, None)."""
    for m in re.finditer(r'<w:style\s+([^>]*)>(.*?)</w:style>', styles_xml, re.DOTALL):
        body = m.group(2)
        name_m = re.search(r'<w:name\s+w:val="([^"]+)"', body)
        if name_m and name_m.group(1) == target_name:
            sid_m = re.search(r'w:styleId="([^"]+)"', m.group(1))
            if sid_m:
                return sid_m.group(1), body
    return None, None


def clone_table_style(ref_styles_xml: str, target_styles_xml: str,
                      ref_style_name: str = "Table Grid",
                      target_style_id: str = "Table") -> tuple:
    """reference 의 <ref_style_name> 스타일 정의를 target 의 <target_style_id> 스타일에
    전체 복사. 자기 자신 name 은 target_style_id 로 유지 (pandoc 매핑 보존).
    basedOn 은 제거해 self-contained 정의로 만든다.

    Returns: (new_styles_xml, source_style_id_used_or_None)"""
    src_id, src_body = find_style_id_by_name(ref_styles_xml, ref_style_name)
    if not src_id:
        return target_styles_xml, None

    # source body 에서 name 과 basedOn 제거 (새 name 박을 거니까)
    new_inner = re.sub(r'<w:name\s+w:val="[^"]+"\s*/>', '', src_body)
    new_inner = re.sub(r'<w:basedOn\s+w:val="[^"]+"\s*/>', '', new_inner)

    # target 의 target_style_id 스타일을 새 body 로 치환
    def repl(m):
        attrs = m.group(1)
        return f'<w:style {attrs}><w:name w:val="{target_style_id}"/>{new_inner}</w:style>'

    pat = rf'<w:style\s+([^>]*w:styleId="{re.escape(target_style_id)}"[^>]*)>.*?</w:style>'
    new_target, n = re.subn(pat, repl, target_styles_xml, count=1, flags=re.DOTALL)
    if n == 0:
        # target 에 해당 styleId 없으면 새로 삽입
        new_style = (
            f'<w:style w:type="table" w:styleId="{target_style_id}" w:customStyle="1">'
            f'<w:name w:val="{target_style_id}"/>{new_inner}</w:style>'
        )
        if '</w:styles>' in target_styles_xml:
            new_target = target_styles_xml.replace('</w:styles>', new_style + '</w:styles>', 1)
        else:
            new_target = target_styles_xml + new_style
    return new_target, src_id


def process_document_xml(doc_xml: str, ref_tblpr_inner: str = None,
                         min_col_twips: int = MIN_COL_TWIPS_DEFAULT):
    """모든 <w:tbl> 에 대해 patch 적용.

    ref_tblpr_inner 가 주어지면 (reference 우선 모드):
        - pandoc 의 tblPr 을 reference 패턴으로 통째 교체 (tblLayout fixed, tblW pct 등 버림)
    아니면 (fallback):
        - pandoc 의 tblPr 은 유지하고 tblLook 만 04A0 으로 패치

    min_col_twips > 0 이면 모든 tblGrid 의 gridCol·tcW(dxa) 너비를 그 값 이상으로 강제.
    """
    count = 0

    def patch_one_table(m):
        nonlocal count
        count += 1
        tbl = m.group(0)
        if ref_tblpr_inner:
            tbl = replace_tblpr_with_reference_pattern(tbl, ref_tblpr_inner)
        else:
            tbl = patch_tblpr_look(tbl)
        tbl = patch_table_cnfstyle(tbl)
        tbl = remove_compact_in_tables(tbl)
        tbl = enforce_min_col_width(tbl, min_twips=min_col_twips)
        return tbl

    new_doc = TBL_RE.sub(patch_one_table, doc_xml)
    return new_doc, count


def postprocess(docx_in: Path, docx_out: Path,
                reference: Path = None,
                ref_style_name: str = "Table Grid",
                target_style_id: str = "Table",
                min_col_twips: int = MIN_COL_TWIPS_DEFAULT) -> dict:
    """Returns: {'tables': N, 'cloned_from': styleId or None, 'mode': 'reference'|'pandoc'}

    우선순위:
        - reference 에 표 스타일 + 표 패턴 있음 → 그것을 정답으로 사용 (pandoc tblPr 통째 교체)
        - 없으면 → pandoc 출력 유지하고 최소 patch (tblLook + cnfStyle) 만 적용
    """
    with zipfile.ZipFile(docx_in) as zin:
        names = zin.namelist()
        contents = {n: zin.read(n) for n in names}

    # 1) reference 가 있으면 먼저 시도: 스타일 클론 + 표 tblPr 패턴 추출
    cloned_from = None
    ref_tblpr_inner = None
    if reference is not None and reference.exists():
        try:
            with zipfile.ZipFile(reference) as zref:
                ref_styles_xml = zref.read('word/styles.xml').decode('utf-8')
                ref_doc_xml = zref.read('word/document.xml').decode('utf-8')

            # 스타일 클론
            target_styles_xml = contents['word/styles.xml'].decode('utf-8')
            new_styles, cloned_from = clone_table_style(
                ref_styles_xml, target_styles_xml,
                ref_style_name=ref_style_name,
                target_style_id=target_style_id,
            )
            contents['word/styles.xml'] = new_styles.encode('utf-8')

            # 표 tblPr 패턴 추출 (reference 의 실제 표에서)
            if cloned_from:
                extracted = extract_reference_tblpr(ref_doc_xml)
                if extracted:
                    ref_tblpr_inner = adjust_tblpr_for_target(extracted, target_style_id)
                    # tblBorders 를 style 에서 추출해 표 tblPr 에 inline 으로 박음
                    # (style inheritance 만으로는 Word 가 border 굵기를 thin 으로 fallback 하는 경우 대비)
                    borders = extract_style_tblborders(ref_styles_xml, ref_style_name)
                    if borders:
                        ref_tblpr_inner = inline_inject_borders_in_tblpr(ref_tblpr_inner, borders)
        except (KeyError, FileNotFoundError):
            pass

    # 2) document.xml 패치
    #    ref_tblpr_inner 있음 → reference 표 패턴으로 tblPr 통째 교체
    #    없음 → pandoc tblPr 유지하고 tblLook 만 패치 (fallback)
    #    + 모든 column 너비를 min_col_twips 이상으로 강제 (기본 1cm)
    doc_xml = contents['word/document.xml'].decode('utf-8')
    new_doc, n_tables = process_document_xml(
        doc_xml, ref_tblpr_inner=ref_tblpr_inner, min_col_twips=min_col_twips,
    )

    contents['word/document.xml'] = new_doc.encode('utf-8')

    with zipfile.ZipFile(docx_out, 'w', zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, contents[name])

    return {
        'tables': n_tables,
        'cloned_from': cloned_from,
        'mode': 'reference' if ref_tblpr_inner else 'pandoc',
    }


def main():
    ap = argparse.ArgumentParser(description="pandoc 변환 후 docx 의 표 디자인 적용")
    ap.add_argument('docx', help="대상 docx (in-place 또는 --out 지정)")
    ap.add_argument('--reference', help="회사 reference docx (스타일 클론 소스)")
    ap.add_argument('--ref-style-name', default="Table Grid",
                    help="reference 에서 클론할 스타일 이름 (기본: 'Table Grid')")
    ap.add_argument('--target-style-id', default="Table",
                    help="변환 docx 의 덮어쓸 styleId (기본: 'Table' — pandoc 출력)")
    ap.add_argument('--no-style-clone', action='store_true',
                    help="스타일 클론 건너뛰기. reference 가 있어도 무시.")
    ap.add_argument('--min-col-cm', type=float, default=1.0,
                    help="모든 표 칼럼/셀(dxa) 너비를 이 값(cm) 이상으로 강제 (기본 1.0). 0 으로 끄기.")
    ap.add_argument('--out', help="별도 출력 경로 (기본: in-place)")
    ap.add_argument('--dry-run', action='store_true', help="패치 안 하고 표 개수만 보고")
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

    if args.dry_run:
        with zipfile.ZipFile(inp) as z:
            doc_xml = z.read('word/document.xml').decode('utf-8')
        n = len(TBL_RE.findall(doc_xml))
        print(f"[POSTPROCESS-DRY] {inp.name}: 표 {n}개 발견")
        return 0

    # reference 결정: --reference 우선, 아니면 스킬 references/ 하위 자동 탐색
    ref_path = None
    if not args.no_style_clone:
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
            print(f"      [POSTPROCESS-WARN] reference 없음 ({ref_path}) — 스타일 클론 건너뜀")
            ref_path = None

    out = Path(args.out) if args.out else inp

    min_twips = int(round(args.min_col_cm * TWIPS_PER_CM))

    def do(in_path, out_path):
        return postprocess(in_path, out_path,
                           reference=ref_path,
                           ref_style_name=args.ref_style_name,
                           target_style_id=args.target_style_id,
                           min_col_twips=min_twips)

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

    print(f"[POSTPROCESS] {inp.name}: 표 {info['tables']}개 패치 ({loc}), mode={info['mode']}")
    if info['mode'] == 'reference':
        print(f"[POSTPROCESS-CLONE] '{args.ref_style_name}' (src styleId={info['cloned_from']}) → '{args.target_style_id}'  + 표 tblPr 패턴 교체")
    else:
        print(f"[POSTPROCESS-CLONE] 생략 (reference 표 스타일 없음 — pandoc 출력 유지, tblLook/cnfStyle 만 패치)")
    if min_twips > 0:
        print(f"[POSTPROCESS-MINW] 모든 칼럼 너비 ≥ {args.min_col_cm}cm ({min_twips} twips) 강제")
    return 0


if __name__ == '__main__':
    sys.exit(main())
