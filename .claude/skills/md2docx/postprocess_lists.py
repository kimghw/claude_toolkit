#!/usr/bin/env python3
"""
md2docx/postprocess_lists.py
  — 변환 docx 의 bullet/list 단락에 reference 의 list paragraph 스타일 속성을
    direct formatting 으로 강제 적용한다.

대상 단락: <w:pPr> 안에 <w:numPr> 가 있는 단락 (pandoc 이 만든 bullet/ordered list).
promote 패턴으로 heading 화된 단락은 numPr 가 없으므로 영향받지 않는다.

reference 에서 사용할 스타일 후보 (우선순위):
    List Paragraph → ListParagraph → List Bullet → List Number

추출 항목 (있는 것만):
    pPr 의 <w:ind .../>      (들여쓰기: left, hanging, firstLine)
    pPr 의 <w:spacing .../>  (줄간격, before/after)
    pPr 의 <w:jc .../>       (정렬)
    rPr 전체                  (폰트, 크기, 색상 등)

적용 규칙:
    - 단락 pPr 내부에 같은 태그(ind/spacing/jc) 가 있으면 reference 값으로 교체.
    - 없으면 </w:pPr> 직전에 삽입.
    - rPr 가 단락 pPr 에 있으면 reference 내용으로 교체, 없으면 추가.

Usage:
    python postprocess_lists.py <docx> --reference <ref.docx>
"""

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path


CANDIDATE_STYLES = ["List Paragraph", "ListParagraph", "List Bullet", "List Number"]


def _find_style_block_by_name(styles_xml, name):
    """name (w:name w:val) 으로 <w:style>...</w:style> 블록 본문 반환. 없으면 None."""
    for m in re.finditer(r"<w:style\s+([^>]*?)>(.*?)</w:style>", styles_xml, re.DOTALL):
        body = m.group(2)
        nm = re.search(r'<w:name\s+w:val="([^"]+)"', body)
        if nm and nm.group(1) == name:
            return body
    return None


def extract_list_props(ref_docx):
    """reference docx 에서 list paragraph 스타일의 pPr 일부 + rPr 추출.

    Returns:
        (chosen_name, props) 또는 (None, None) 후보 스타일 모두 없을 때.
        props = {"ppr_elements": [<w:ind/>, <w:spacing/>, ...], "rpr_inner": "..." | None}
    """
    try:
        with zipfile.ZipFile(ref_docx) as z:
            styles_xml = z.read("word/styles.xml").decode("utf-8")
    except (FileNotFoundError, zipfile.BadZipFile, KeyError):
        return None, None

    chosen = None
    body = None
    for cand in CANDIDATE_STYLES:
        b = _find_style_block_by_name(styles_xml, cand)
        if b is not None:
            chosen = cand
            body = b
            break

    if body is None:
        return None, None

    ppr_elements = []
    for tag in ("ind", "spacing", "jc"):
        m = re.search(rf'<w:{tag}\b[^/>]*/>', body)
        if m:
            ppr_elements.append(m.group(0))

    rpr_m = re.search(r"<w:rPr>(.*?)</w:rPr>", body, re.DOTALL)
    rpr_inner = rpr_m.group(1) if rpr_m else None

    return chosen, {"ppr_elements": ppr_elements, "rpr_inner": rpr_inner}


def _patch_ppr(ppr_xml, ppr_elements, rpr_inner):
    """단일 <w:pPr>...</w:pPr> 본문에 props 적용."""
    new = ppr_xml
    for elt in ppr_elements:
        tag_m = re.match(r"<w:(\w+)", elt)
        if not tag_m:
            continue
        tag = tag_m.group(1)
        new = re.sub(rf'<w:{tag}\b[^/>]*/>', "", new)

    insertion = "".join(ppr_elements)
    if insertion:
        if new.endswith("</w:pPr>"):
            new = new[: -len("</w:pPr>")] + insertion + "</w:pPr>"
        else:
            new = new + insertion

    if rpr_inner is not None:
        if "<w:rPr>" in new:
            new = re.sub(
                r"<w:rPr>.*?</w:rPr>",
                f"<w:rPr>{rpr_inner}</w:rPr>",
                new,
                count=1,
                flags=re.DOTALL,
            )
        else:
            if new.endswith("</w:pPr>"):
                new = new[: -len("</w:pPr>")] + f"<w:rPr>{rpr_inner}</w:rPr>" + "</w:pPr>"
            else:
                new = new + f"<w:rPr>{rpr_inner}</w:rPr>"

    return new


PPR_RE = re.compile(r"<w:pPr>(.*?)</w:pPr>", re.DOTALL)


def patch_document_xml(doc_xml, props):
    """<w:numPr> 를 포함한 단락의 <w:pPr> 본문에 props 를 강제 적용. (n_patched 반환)"""
    ppr_elements = props["ppr_elements"]
    rpr_inner = props["rpr_inner"]
    if not ppr_elements and rpr_inner is None:
        return doc_xml, 0

    patched = [0]

    def repl(m):
        inner = m.group(1)
        if "<w:numPr>" not in inner:
            return m.group(0)
        new_inner = _patch_ppr(inner, ppr_elements, rpr_inner)
        if new_inner != inner:
            patched[0] += 1
        return f"<w:pPr>{new_inner}</w:pPr>"

    new_doc = PPR_RE.sub(repl, doc_xml)
    return new_doc, patched[0]


def process(docx_path, ref_docx):
    chosen, props = extract_list_props(ref_docx)
    if props is None:
        print(f"[POSTPROCESS-LISTS] reference 에 list paragraph 후보 스타일 없음 — skip")
        return 0

    if not props["ppr_elements"] and props["rpr_inner"] is None:
        print(f"[POSTPROCESS-LISTS] reference '{chosen}' 에 적용 가능한 ind/spacing/jc/rPr 없음 — skip")
        return 0

    summary = []
    for e in props["ppr_elements"]:
        tag = re.match(r"<w:(\w+)", e)
        if tag:
            summary.append(tag.group(1))
    if props["rpr_inner"] is not None:
        summary.append("rPr")
    print(f"[POSTPROCESS-LISTS] reference '{chosen}' 에서 추출: {', '.join(summary) or '(none)'}")

    tmp = docx_path.with_suffix(docx_path.suffix + ".tmp")
    n_patched = 0
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.namelist():
            data = zin.read(item)
            if item == "word/document.xml":
                doc_xml = data.decode("utf-8")
                new_doc, n_patched = patch_document_xml(doc_xml, props)
                data = new_doc.encode("utf-8")
            zout.writestr(item, data)

    shutil.move(str(tmp), str(docx_path))
    print(f"[POSTPROCESS-LISTS] {docx_path.name}: list 단락 {n_patched}개 패치 (in-place)")
    return n_patched


def main():
    ap = argparse.ArgumentParser(description="bullet/list 단락에 reference 의 list paragraph 스타일 강제 적용")
    ap.add_argument("docx", help="post-processing 대상 docx (in-place 수정)")
    ap.add_argument("--reference", required=True, metavar="DOCX", help="reference docx")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    docx = Path(args.docx)
    ref = Path(args.reference)
    if not docx.exists():
        print(f"ERROR: not found: {docx}", file=sys.stderr)
        return 1
    if not ref.exists():
        print(f"ERROR: --reference not found: {ref}", file=sys.stderr)
        return 1

    process(docx, ref)
    return 0


if __name__ == "__main__":
    sys.exit(main())
