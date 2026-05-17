#!/usr/bin/env python3
"""
md2docx/userlist_scan_lists.py
  — pandoc 출력 docx 의 numPr 리스트를 list_kind(numFmt + ilvl) 별로 그룹화해 dump.

설계 원칙
=========
postprocess_userlist 가 적용할 매핑(`userlist-mapping.json`)을 만들기 위한 사전 관찰자.
사용자에게 "level-0 bullet 은 어떤 cluster?" 식으로 묻기 전에, 실제 pandoc 가 만들어
낸 list_kind 들이 무엇인지 LLM 이 알아야 한다. 이 스크립트는 단지 raw 통계만 dump
하고 판정·매핑은 LLM 이 catalog 와 함께 보고 수행.

매칭 단위 = (numFmt, ilvl). 같은 (numFmt, ilvl) 의 모든 paragraph 가 한 list_kind 로
묶인다. numId 는 참고용 (같은 .md 리스트 블록을 식별).

Usage:
    python userlist_scan_lists.py <output.docx> --out <scan.json>

종료 코드:
    0 numPr 리스트 0건
    7 numPr 리스트 1건 이상 (LLM 매핑 결정 필요)
"""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _build_numid_kind_map(numbering_xml):
    """numId → (numFmt, abstract_id) 매핑. ilvl=0 의 numFmt 기준."""
    if not numbering_xml:
        return {}
    abs_fmt = {}
    for m in re.finditer(
        r'<w:abstractNum\s+[^>]*w:abstractNumId="(\d+)"[^>]*>(.*?)</w:abstractNum>',
        numbering_xml,
        re.DOTALL,
    ):
        abs_id = m.group(1)
        body = m.group(2)
        lvl_m = re.search(
            r'<w:lvl\s+[^>]*w:ilvl="0"[^>]*>(.*?)</w:lvl>', body, re.DOTALL
        )
        if not lvl_m:
            continue
        fmt_m = re.search(r'<w:numFmt\s+[^>]*w:val="([^"]+)"', lvl_m.group(1))
        if fmt_m:
            abs_fmt[abs_id] = fmt_m.group(1)

    out = {}
    for m in re.finditer(
        r'<w:num\s+[^>]*w:numId="(\d+)"[^>]*>(.*?)</w:num>',
        numbering_xml,
        re.DOTALL,
    ):
        num_id = m.group(1)
        body = m.group(2)
        ref_m = re.search(r'<w:abstractNumId\s+[^>]*w:val="(\d+)"', body)
        if not ref_m:
            continue
        abs_id = ref_m.group(1)
        fmt = abs_fmt.get(abs_id, "unknown")
        out[num_id] = (fmt, abs_id)
    return out


P_RE = re.compile(r"<w:p\b[^>]*>(.*?)</w:p>", re.DOTALL)
PPR_RE = re.compile(r"<w:pPr>(.*?)</w:pPr>", re.DOTALL)
NUMPR_BLOCK_RE = re.compile(r"<w:numPr\b[^>]*>(.*?)</w:numPr>", re.DOTALL)


def _read_numpr(ppr_inner):
    m = NUMPR_BLOCK_RE.search(ppr_inner)
    if not m:
        if re.search(r"<w:numPr\b[^/>]*/>", ppr_inner):
            return (None, "0")
        return (None, None)
    body = m.group(1)
    nid_m = re.search(r'<w:numId\s+[^>]*w:val="(\d+)"', body)
    ilvl_m = re.search(r'<w:ilvl\s+[^>]*w:val="(\d+)"', body)
    nid = nid_m.group(1) if nid_m else None
    ilvl = ilvl_m.group(1) if ilvl_m else "0"
    return (nid, ilvl)


def _para_text(p_xml):
    parts = re.findall(r"<w:t\b[^>]*>(.*?)</w:t>", p_xml, re.DOTALL)
    return "".join(parts)


def _short(s, n):
    s = (s or "").replace("\n", " ").replace("\r", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def scan(docx_path):
    """numPr 단락을 (numFmt, ilvl) 별로 묶어 list_kind dump."""
    with zipfile.ZipFile(docx_path) as z:
        doc_xml = z.read("word/document.xml").decode("utf-8")
        try:
            numbering_xml = z.read("word/numbering.xml").decode("utf-8")
        except KeyError:
            numbering_xml = ""

    numid_to_fmt = _build_numid_kind_map(numbering_xml)

    # (numFmt, ilvl) → cluster bucket
    buckets = {}
    # numId 별 통계 (참고용)
    by_numid = {}

    for p_m in P_RE.finditer(doc_xml):
        p_xml = p_m.group(0)
        ppr_m = PPR_RE.search(p_xml)
        if not ppr_m or "<w:numPr" not in ppr_m.group(1):
            continue
        nid, ilvl = _read_numpr(ppr_m.group(1))
        if nid is None and ilvl is None:
            continue
        fmt_info = numid_to_fmt.get(nid) if nid else None
        num_fmt = fmt_info[0] if fmt_info else "unknown"
        kind = "unordered" if num_fmt == "bullet" else "ordered"
        ilvl = ilvl or "0"

        text = _para_text(p_xml).strip()
        key = (num_fmt, ilvl)
        bucket = buckets.setdefault(key, {
            "numFmt": num_fmt,
            "ilvl": ilvl,
            "kind": kind,
            "count": 0,
            "sample_text": text or "",
            "alt_samples": [],
            "numIds": set(),
        })
        bucket["count"] += 1
        if nid:
            bucket["numIds"].add(nid)
        if text and len(bucket["alt_samples"]) < 3 and text != bucket["sample_text"]:
            bucket["alt_samples"].append(_short(text, 80))

        nbucket = by_numid.setdefault(nid or "?", {
            "numFmt": num_fmt, "kind": kind, "ilvls": set(), "count": 0,
        })
        nbucket["ilvls"].add(ilvl)
        nbucket["count"] += 1

    # 정렬: numFmt 기본 순서(bullet 먼저), ilvl 오름차순
    def _key(item):
        fmt = item[0][0]
        priority = 0 if fmt == "bullet" else (1 if fmt == "decimal" else 2)
        return (priority, fmt, int(item[0][1]) if item[0][1].isdigit() else 99)

    items = sorted(buckets.items(), key=_key)
    list_kinds = []
    for (num_fmt, ilvl), b in items:
        list_kinds.append({
            "numFmt": num_fmt,
            "ilvl": ilvl,
            "kind": b["kind"],
            "count": b["count"],
            "sample_text": _short(b["sample_text"], 80),
            "alt_samples": b["alt_samples"],
            "numIds": sorted(b["numIds"], key=lambda x: int(x) if x.isdigit() else 0),
        })

    return list_kinds, by_numid


def main():
    ap = argparse.ArgumentParser(
        description="pandoc 출력 docx 의 numPr 리스트를 list_kind 별로 dump"
    )
    ap.add_argument("docx", help="스캔 대상 docx (pandoc 출력)")
    ap.add_argument("--out", required=True, metavar="JSON", help="스캔 결과 저장 경로")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    docx = Path(args.docx)
    out = Path(args.out)
    if not docx.exists():
        print(f"ERROR: not found: {docx}", file=sys.stderr)
        return 1

    try:
        list_kinds, by_numid = scan(docx)
    except zipfile.BadZipFile as e:
        print(f"ERROR: bad docx: {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"ERROR: word/document.xml 없음: {e}", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"list_kinds": list_kinds}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for lk in list_kinds:
        alt = f" | alt={lk['alt_samples']}" if lk["alt_samples"] else ""
        nids = f" | numIds={lk['numIds']}" if lk["numIds"] else ""
        print(
            f"[USERLIST-PANDOC-LIST] numFmt={lk['numFmt']} ilvl={lk['ilvl']} | "
            f"kind={lk['kind']} | count={lk['count']} | "
            f"sample='{lk['sample_text']}'{alt}{nids}"
        )
    print(f"[USERLIST-PANDOC-LIST-COUNT] kinds={len(list_kinds)}")
    print(f"[USERLIST-SCAN-OUT] {out.resolve()}")
    return 7 if list_kinds else 0


if __name__ == "__main__":
    sys.exit(main())
