#!/usr/bin/env python3
"""postprocess_inline_basedon.py

map.py 가 만든 매핑 스타일은 `<w:basedOn>` 만 갖고 pPr/rPr 은 부모에서
상속받게 둔다. 구조적으로는 OOXML 표준이지만 Word 가 customStyle 의 basedOn
체인을 시각적 렌더링에 일부 적용하지 못하는 케이스가 있어, 단락에 pStyle 만
지정해도 회사 양식 (자동 번호·정렬·굵게·크기) 이 적용되지 않는다.

이 후처리는 styles.xml 의 각 스타일에 대해 basedOn 체인을 root → leaf 로
순회하면서 pPr 자식·rPr 자식을 같은 tag 끼리 leaf 가 이기는 규칙으로 병합한
뒤, leaf 스타일에 직접 인라인으로 적어 넣는다. 결과적으로 각 스타일이
self-contained 가 되어 Word 가 chain 을 재귀 해소할 필요 없이 바로 렌더.

대상: 모든 customStyle (map.py 가 만든 Heading1/Heading2/... 포함). basedOn
이 없거나 체인 길이가 1 이면 변경 없음.

Usage:
    python postprocess_inline_basedon.py <docx>
"""

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


CHILD_RE = re.compile(
    r'<w:(\w+)(?:\s[^>]*?)?(?:/>|>.*?</w:\1>)',
    re.DOTALL,
)
STYLE_RE = re.compile(r'<w:style\s+[^>]*>.*?</w:style>', re.DOTALL)
STYLE_ID_RE = re.compile(r'w:styleId="([^"]+)"')
BASED_ON_RE = re.compile(r'<w:basedOn\s+w:val="([^"]+)"\s*/>')
PPR_RE = re.compile(r'<w:pPr\b[^>]*>.*?</w:pPr>', re.DOTALL)
RPR_RE = re.compile(r'<w:rPr\b[^>]*>.*?</w:rPr>', re.DOTALL)


def _extract_children(block):
    """`<w:pPr>...</w:pPr>` 또는 `<w:rPr>...</w:rPr>` 블록의 inner children 을
    (tag, full_xml) 리스트로 반환. 같은 tag 가 여러 번 나오면 마지막 것만 살림."""
    if not block:
        return []
    inner_m = re.search(r'^<w:\w+\b[^>]*>(.*)</w:\w+>$', block, re.DOTALL)
    if not inner_m:
        return []
    content = inner_m.group(1)
    results = []
    pos = 0
    while pos < len(content):
        # 공백/개행 스킵
        ws_m = re.match(r'\s+', content[pos:])
        if ws_m:
            pos += ws_m.end()
            continue
        m = CHILD_RE.match(content, pos)
        if not m:
            break
        results.append((m.group(1), m.group(0)))
        pos = m.end()
    return results


def _merge_children(merged_dict, order, source_children):
    """leaf 가 이기는 규칙으로 dict 에 병합. order 는 첫 등장 순서 추적."""
    for tag, xml in source_children:
        if tag not in merged_dict:
            order.append(tag)
        merged_dict[tag] = xml


def _build_block(kind, merged_dict, order):
    """`<w:pPr>` 또는 `<w:rPr>` 블록을 children dict 로부터 재구성."""
    if not merged_dict:
        return ""
    return f"<w:{kind}>" + "".join(merged_dict[t] for t in order) + f"</w:{kind}>"


def _index_styles(styles_xml):
    """styleId → style 블록 텍스트."""
    out = {}
    for m in STYLE_RE.finditer(styles_xml):
        sid_m = STYLE_ID_RE.search(m.group(0))
        if sid_m:
            out[sid_m.group(1)] = m.group(0)
    return out


def _basedon(block):
    m = BASED_ON_RE.search(block)
    return m.group(1) if m else None


def _walk_chain(leaf_id, index):
    """root → leaf 순서의 styleId 목록."""
    chain = []
    seen = set()
    cur = leaf_id
    while cur and cur in index and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        cur = _basedon(index[cur])
    return list(reversed(chain))


def _extract_pPr_rPr(block):
    pm = PPR_RE.search(block)
    rm = RPR_RE.search(block)
    return (pm.group(0) if pm else None), (rm.group(0) if rm else None)


def _replace_pPr_rPr_in_style(block, new_pPr, new_rPr):
    """style 블록에서 기존 pPr/rPr 을 제거하고 새 값을 </w:style> 직전에 삽입."""
    # 기존 pPr/rPr 제거
    block = PPR_RE.sub("", block, count=1)
    block = RPR_RE.sub("", block, count=1)
    insert = (new_pPr or "") + (new_rPr or "")
    if not insert:
        return block
    end_idx = block.rfind("</w:style>")
    if end_idx < 0:
        return block
    return block[:end_idx] + insert + block[end_idx:]


def inline_basedon(styles_xml: str) -> tuple[str, int]:
    """styles.xml 의 basedOn 체인을 가진 모든 스타일에 인라인 베이킹.

    반환: (변경된 styles_xml, 처리된 스타일 개수).
    """
    index = _index_styles(styles_xml)
    modified_blocks = {}  # styleId → new block string
    processed = 0
    for sid, block in index.items():
        if _basedon(block) is None:
            continue
        chain = _walk_chain(sid, index)
        if len(chain) < 2:
            continue

        pPr_merged = {}
        pPr_order = []
        rPr_merged = {}
        rPr_order = []
        for cid in chain:
            cblock = index[cid]
            cppr, crpr = _extract_pPr_rPr(cblock)
            _merge_children(pPr_merged, pPr_order, _extract_children(cppr))
            _merge_children(rPr_merged, rPr_order, _extract_children(crpr))

        # leaf 스타일에만 적용. root → leaf 의 모든 자식을 leaf 에 넣는다.
        if not pPr_merged and not rPr_merged:
            continue
        new_pPr = _build_block("pPr", pPr_merged, pPr_order)
        new_rPr = _build_block("rPr", rPr_merged, rPr_order)
        new_block = _replace_pPr_rPr_in_style(block, new_pPr, new_rPr)
        if new_block != block:
            modified_blocks[sid] = new_block
            processed += 1

    if not modified_blocks:
        return styles_xml, 0

    # 원본 순서를 유지하면서 치환
    new_xml = styles_xml
    for sid, new_block in modified_blocks.items():
        old_block = index[sid]
        new_xml = new_xml.replace(old_block, new_block, 1)

    return new_xml, processed


def _replace_in_zip(zip_path: Path, member: str, new_data: bytes):
    tmp = tempfile.NamedTemporaryFile(
        delete=False, suffix=".docx", dir=str(zip_path.parent)
    )
    tmp.close()
    tmp_path = Path(tmp.name)
    try:
        with zipfile.ZipFile(zip_path, "r") as zin, zipfile.ZipFile(
            tmp_path, "w", zipfile.ZIP_DEFLATED
        ) as zout:
            for item in zin.infolist():
                if item.filename == member:
                    zout.writestr(item, new_data)
                else:
                    zout.writestr(item, zin.read(item.filename))
        shutil.move(str(tmp_path), str(zip_path))
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def main():
    ap = argparse.ArgumentParser(
        description="styles.xml 의 customStyle basedOn 체인을 인라인 베이킹"
    )
    ap.add_argument("docx", help="대상 docx")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    docx = Path(args.docx)
    if not docx.exists():
        print(f"ERROR: not found: {docx}", file=sys.stderr)
        return 1

    with zipfile.ZipFile(docx) as z:
        styles = z.read("word/styles.xml").decode("utf-8")

    new_styles, count = inline_basedon(styles)
    if count == 0:
        print("[POSTPROCESS-INLINE-BASEDON] 처리 대상 없음 — 변경 없음")
        return 0

    _replace_in_zip(docx, "word/styles.xml", new_styles.encode("utf-8"))
    print(f"[POSTPROCESS-INLINE-BASEDON] {count}개 스타일에 basedOn 체인 pPr/rPr 인라인 베이킹")
    return 0


if __name__ == "__main__":
    sys.exit(main())
