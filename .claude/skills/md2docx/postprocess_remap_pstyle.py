#!/usr/bin/env python3
"""postprocess_remap_pstyle.py

map.py 는 pandoc 어휘(`Heading 1`, `Heading 2`, ...) 를 위해 회사 원본
스타일(예: styleId='1', '2', ...) 을 basedOn 으로 상속하는 customStyle 을
새로 추가한다 (case_mismatch 처리). 결과 document.xml 의 heading 단락은
`<w:pStyle w:val="Heading1"/>` 을 갖고, 시각적으론 회사 양식이 적용되지만
Word 의 빠른 스타일 갤러리/스타일 표시 패널에서는 회사 원본 항목
(예: "제 1 편 제목") 이 하이라이트되지 않는다. customStyle 에 `<w:qFormat/>`
이 없으면 갤러리 자체에 나타나지 않기 때문.

이 후처리는 styles.xml 에서 `이름이 basedOn 대상과 대소문자만 다른`
customStyle (case_mismatch alias) 만 골라, document.xml 의 그 pStyle 참조를
basedOn 대상 styleId 로 치환한다. 결과:

  - heading 단락이 회사 원본 styleId 를 직접 사용 → 갤러리에서 회사 항목 하이라이트
  - 자동 번호/들여쓰기/굵게 등 모든 시각 효과는 회사 원본 정의 그대로 (변화 없음)
  - stub 스타일(SourceCode, Caption 등) 과 semantic match (Compact ← List Paragraph,
    Table ← Table Grid) 는 이름이 다르므로 remap 대상이 아님 → 그대로 둠
    (이런 customStyle 은 postprocess_inline_basedon.py 가 self-contained 로
    만들어 시각적으론 동작함)

Usage:
    python postprocess_remap_pstyle.py <docx>
"""

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


STYLE_RE = re.compile(r'<w:style\s+[^>]*>.*?</w:style>', re.DOTALL)
STYLE_ID_RE = re.compile(r'w:styleId="([^"]+)"')
NAME_RE = re.compile(r'<w:name\s+w:val="([^"]+)"')
BASED_ON_RE = re.compile(r'<w:basedOn\s+w:val="([^"]+)"\s*/>')
CUSTOM_RE = re.compile(r'w:customStyle="1"')


def find_remap(styles_xml: str) -> dict[str, str]:
    """case_mismatch alias customStyle → 원본 styleId 매핑."""
    index = {}
    for m in STYLE_RE.finditer(styles_xml):
        block = m.group(0)
        sid_m = STYLE_ID_RE.search(block)
        if not sid_m:
            continue
        sid = sid_m.group(1)
        name_m = NAME_RE.search(block)
        based_m = BASED_ON_RE.search(block)
        index[sid] = {
            "name": name_m.group(1) if name_m else None,
            "basedOn": based_m.group(1) if based_m else None,
            "custom": bool(CUSTOM_RE.search(block)),
        }

    remap = {}
    for sid, info in index.items():
        if not info["custom"] or not info["basedOn"]:
            continue
        target = index.get(info["basedOn"])
        if not target:
            continue
        if (
            info["name"]
            and target["name"]
            and info["name"].lower() == target["name"].lower()
        ):
            remap[sid] = info["basedOn"]
    return remap


def remap_document(document_xml: str, remap: dict[str, str]) -> tuple[str, int]:
    """document.xml 의 pStyle 참조 치환."""
    total = 0
    new_xml = document_xml
    for old_id, new_id in remap.items():
        pat = re.compile(
            rf'<w:pStyle\s+w:val="{re.escape(old_id)}"\s*/>'
        )
        new_xml, n = pat.subn(f'<w:pStyle w:val="{new_id}"/>', new_xml)
        total += n
    return new_xml, total


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
        description="document.xml 의 case_mismatch alias pStyle 참조를 원본 styleId 로 치환"
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
        doc = z.read("word/document.xml").decode("utf-8")

    remap = find_remap(styles)
    if not remap:
        print("[POSTPROCESS-REMAP-PSTYLE] case_mismatch alias 없음 — 변경 없음")
        return 0

    new_doc, total = remap_document(doc, remap)
    if total == 0:
        print(
            f"[POSTPROCESS-REMAP-PSTYLE] 후보 alias {len(remap)}개 있으나 document.xml 에서 참조 없음 — 변경 없음"
        )
        return 0

    _replace_in_zip(docx, "word/document.xml", new_doc.encode("utf-8"))
    items = ", ".join(f"{k}→{v}" for k, v in sorted(remap.items()))
    print(
        f"[POSTPROCESS-REMAP-PSTYLE] {total}개 pStyle 참조 치환 (회사 원본 styleId 로 정규화). 매핑: {items}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
