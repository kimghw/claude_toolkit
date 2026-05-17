#!/usr/bin/env python3
"""postprocess_style_numbering.py

Pandoc 의 `--reference-doc` 처리는 reference 의 numbering.xml 을 그대로 쓰지
않고 자체적으로 재작성하면서 numId 를 1000+ 로 재번호한다. 그 결과 회사
reference 의 heading/body 스타일 정의(`<w:pPr><w:numPr><w:numId w:val="2"/>`)
가 가리키는 numId 가 출력 docx 의 numbering.xml 에서 사라져 자동 번호
(예: heading 1 → "제 %1 편")가 적용되지 않는 문제가 발생한다.

이 후처리는 다음을 수행한다:
  1) 출력 docx 의 styles.xml 을 스캔해 모든 style 이 참조하는 numId 집합을 수집
  2) 출력 docx 의 numbering.xml 에 그 numId 정의가 누락됐는지 확인
  3) 누락된 numId 와 그것이 가리키는 abstractNum 정의를 reference 의
     numbering.xml 에서 복사해 출력에 주입
  4) abstractNum 은 schema 규약상 num 보다 앞에 와야 하므로 첫 <w:num>
     앞에 삽입, num 은 </w:numbering> 직전에 추가

ID 충돌은 검사 후 건너뛴다 (출력에 이미 같은 numId 가 있으면 그건 다른 정의로
간주, 덮어쓰지 않음). 현재 케이스에서 reference 의 heading numId(=2) 와
pandoc 의 markdown 리스트 numIds(1000+) 는 충돌하지 않는다.

Usage:
    python postprocess_style_numbering.py <output.docx> --reference <ref.docx>
"""

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


STYLE_NUMID_RE = re.compile(r'<w:numId\s+w:val="(\d+)"')
EXISTING_NUM_RE = re.compile(r'<w:num\s+w:numId="(\d+)"')
EXISTING_ABSTRACT_RE = re.compile(r'<w:abstractNum\s+w:abstractNumId="(\d+)"')
NUM_ABSTRACTID_RE = re.compile(r'<w:abstractNumId\s+w:val="(\d+)"')


def _num_block_re(nid):
    return re.compile(rf'<w:num\s+w:numId="{re.escape(nid)}"[^>]*>.*?</w:num>', re.DOTALL)


def _abstract_block_re(aid):
    return re.compile(
        rf'<w:abstractNum\s+w:abstractNumId="{re.escape(aid)}"[^>]*>.*?</w:abstractNum>',
        re.DOTALL,
    )


def restore(out_docx: Path, ref_docx: Path) -> tuple[int, list[str]]:
    """누락된 style-참조 numId 정의를 reference 에서 복원.

    반환: (주입된 numId 개수, 주입된 numId 목록)
    """
    with zipfile.ZipFile(ref_docx) as rz:
        ref_numbering = rz.read("word/numbering.xml").decode("utf-8")
    with zipfile.ZipFile(out_docx) as oz:
        out_styles = oz.read("word/styles.xml").decode("utf-8")
        out_numbering = oz.read("word/numbering.xml").decode("utf-8")

    needed = set(STYLE_NUMID_RE.findall(out_styles))
    existing_nums = set(EXISTING_NUM_RE.findall(out_numbering))
    missing = needed - existing_nums
    if not missing:
        return 0, []

    existing_abstracts = set(EXISTING_ABSTRACT_RE.findall(out_numbering))

    new_abstracts = []
    new_nums = []
    injected = []

    for nid in sorted(missing, key=lambda x: int(x) if x.isdigit() else 0):
        m = _num_block_re(nid).search(ref_numbering)
        if not m:
            continue
        num_block = m.group(0)
        am = NUM_ABSTRACTID_RE.search(num_block)
        aid = am.group(1) if am else None

        # abstractNum 복사 (중복이면 스킵)
        if aid and aid not in existing_abstracts:
            am_block = _abstract_block_re(aid).search(ref_numbering)
            if am_block:
                new_abstracts.append(am_block.group(0))
                existing_abstracts.add(aid)

        new_nums.append(num_block)
        injected.append(nid)

    if not new_nums:
        return 0, []

    # abstractNum 은 num 보다 앞에 와야 한다. 첫 <w:num> 위치 앞에 삽입.
    if new_abstracts:
        first_num_idx = out_numbering.find("<w:num ")
        if first_num_idx < 0:
            first_num_idx = out_numbering.find("</w:numbering>")
        if first_num_idx >= 0:
            out_numbering = (
                out_numbering[:first_num_idx]
                + "".join(new_abstracts)
                + out_numbering[first_num_idx:]
            )
        else:
            out_numbering += "".join(new_abstracts)

    # num 은 </w:numbering> 직전에 추가
    end_idx = out_numbering.find("</w:numbering>")
    if end_idx >= 0:
        out_numbering = out_numbering[:end_idx] + "".join(new_nums) + out_numbering[end_idx:]
    else:
        out_numbering += "".join(new_nums)

    _replace_in_zip(out_docx, "word/numbering.xml", out_numbering.encode("utf-8"))
    return len(injected), injected


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
        description="pandoc 출력 docx 에 누락된 style-참조 numbering 정의 복원"
    )
    ap.add_argument("output", help="대상 출력 docx")
    ap.add_argument("--reference", required=True, help="매핑된 reference docx (소스)")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    out = Path(args.output)
    ref = Path(args.reference)
    if not out.exists():
        print(f"ERROR: output not found: {out}", file=sys.stderr)
        return 1
    if not ref.exists():
        print(f"ERROR: reference not found: {ref}", file=sys.stderr)
        return 1

    count, nids = restore(out, ref)
    if count == 0:
        print(
            f"[POSTPROCESS-STYLE-NUM] 누락된 style 참조 numId 없음 — 변경 없음"
        )
    else:
        print(
            f"[POSTPROCESS-STYLE-NUM] reference 에서 numId {nids} 정의 복원 "
            f"(총 {count}개) — heading 자동 번호 복구"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
