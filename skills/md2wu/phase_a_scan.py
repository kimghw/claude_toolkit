#!/usr/bin/env python3
"""Phase A orchestrator — walk UR/*_md and run heading_tokens on each MD.

Usage: phase_a_scan.py <source_dir> <session_id>

Writes:
  queue/sessions/<session_id>/scan/scan_index.json
  queue/sessions/<session_id>/parts/doc_parts.json   (single consolidated file,
                                                       items[<item_id>].headings)
"""

import json
import os
import re
import sys
import uuid
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heading_tokens as ht


WORKROOT = Path("/mnt/c/shared_wk/ontology_iacs/skill_md2wu")


def slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r'[\s\-/\.]', '_', s)
    s = re.sub(r'[^a-z0-9_]', '', s)
    s = re.sub(r'_+', '_', s).strip('_')
    return s


REV_RE = re.compile(r'rev[_\-\.]?(\d+)', re.IGNORECASE)
CORR_RE = re.compile(r'corr[_\-\.]?(\d+)', re.IGNORECASE)
SERIES_RE = re.compile(r'^ur[_\-]?([a-z])(\d+(?:[_\.]\d+)*)(.*)$', re.IGNORECASE)


def parse_filename(stem: str):
    """Extract (series, doc_num, revision, subnum_key) from filename stem."""
    low = stem.lower()
    low = re.sub(r'-+', '-', low)
    m = SERIES_RE.match(low)
    if not m:
        return None, None, None, None, slug(stem)
    letter = m.group(1)          # z
    numpart = m.group(2)         # 10.3 / 7.1 / 1 / 106 (no dot)
    rest = m.group(3)            # '-rev.21-aug-2023-cln' or 'rev25' or 'del'

    # Handle cases like 'z101rev25' where 10.1 was collapsed to 101.
    # Heuristic: if numpart has no dot/underscore and len >= 3, try splitting.
    if '.' not in numpart and '_' not in numpart and len(numpart) >= 3:
        # Check if first 2 digits + '.' + remainder matches a known pattern.
        # Prior convention used z10_1 for 'z101'. Split: first 2 digits, rest.
        nstr = numpart
        # Only split if starts with a number >= 10 (plausible big series).
        if int(nstr[:2]) >= 10 and len(nstr) in (3, 4):
            # Split as XX.Y or XX.YY
            numpart = nstr[:2] + '.' + nstr[2:]
    # Normalize to underscore form
    doc_num = numpart.replace('.', '_')

    rev_m = REV_RE.search(rest)
    corr_m = CORR_RE.search(rest)
    revision = rev_m.group(1) if rev_m else None
    corr = corr_m.group(1) if corr_m else None

    # series_order: tuple of ints from numpart
    nums = [int(x) for x in numpart.replace('.', ' ').replace('_', ' ').split()]
    while len(nums) < 4:
        nums.append(0)
    series_order = tuple(nums)

    # Build suffix
    suffix_parts = []
    if revision:
        suffix_parts.append(f"rev{revision}")
    elif 'del' in rest:
        suffix_parts.append("del")
    elif 'new' in rest:
        suffix_parts.append("new")
    if corr:
        suffix_parts.append(f"corr{corr}")
    suffix = '_'.join(suffix_parts)

    # doc_specific_key: z10_3_rev21 etc.
    parts = [f"{letter}{doc_num.split('_')[0]}"]
    sub_nums = doc_num.split('_')[1:]
    for sn in sub_nums:
        parts.append(sn)
    if suffix:
        parts.append(suffix)
    doc_specific = '_'.join(parts)
    # Ensure lang suffix
    doc_specific_en = f"{doc_specific}_en"

    return letter, doc_num, revision, series_order, doc_specific_en


def main():
    source_dir = Path(sys.argv[1]).resolve()
    session_id = sys.argv[2]

    scan_dir = WORKROOT / "queue" / "sessions" / session_id / "scan"
    parts_dir = WORKROOT / "queue" / "sessions" / session_id / "parts"
    scan_dir.mkdir(parents=True, exist_ok=True)
    parts_dir.mkdir(parents=True, exist_ok=True)

    encode_fn, measure_method = ht.get_encoder()

    md_files = sorted(source_dir.glob("UR_*_md/*.md"))
    print(f"Found {len(md_files)} MD files under {source_dir}")

    files_entry = []
    total_tokens = 0
    by_series = {}
    errors_any = []
    warnings_any = []
    doc_parts_items = {}  # item_id -> {"headings": [...], "chunk_plan": null}

    for md_file in md_files:
        stem = md_file.stem
        letter, doc_num, revision, series_order, doc_specific_en = parse_filename(stem)
        if letter is None:
            print(f"SKIP (unparseable): {md_file.name}")
            continue

        item_id = f"iacs_ur_{doc_specific_en}"
        document_key = f"iacs_ur_{letter}{doc_num}" if doc_num else f"iacs_ur_{letter}"

        with open(md_file, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        lines = [l.rstrip("\n") for l in lines]
        total_lines = len(lines)

        headings = ht.parse_headings(lines)
        if not headings:
            full_text = "\n".join(lines)
            tokens = len(encode_fn(full_text))
            headings = [{
                "level": 1, "start_line": 1, "end_line": total_lines,
                "title": "(no heading)", "parent_id": "",
                "heading_id": f"{document_key}_HD_001",
                "est_tokens_inclusive": tokens,
                "est_tokens_exclusive": tokens,
            }]
        else:
            for idx, h in enumerate(headings):
                h["heading_id"] = f"{document_key}_HD_{idx + 1:03d}"
            headings = ht.build_tree(headings, total_lines)
            headings = ht.measure_tokens(headings, lines, encode_fn)

        errs, warns = ht.verify_additivity(headings)
        if errs:
            errors_any.append({"item": item_id, "errors": errs})
        if warns:
            warnings_any.append({"item": item_id, "warnings": warns})

        doc_parts_items[item_id] = {
            "headings": headings,
            "chunk_plan": None,
        }

        cost_tokens = headings[0]["est_tokens_inclusive"]
        total_tokens += cost_tokens
        by_series.setdefault(letter, []).append(item_id)

        files_entry.append({
            "item_id": item_id,
            "document_key": document_key,
            "filepath": str(md_file),
            "cost_tokens": cost_tokens,
            "heading_count": len(headings),
            "source_family": "iacs_ur",
            "series": f"ur_{letter}",
            "series_order": list(series_order),
            "revision": revision,
        })

    files_entry.sort(key=lambda e: (e["series"], tuple(e["series_order"]), e["item_id"]))

    scan_index = {
        "scan_id": dt.datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "source_dir": str(source_dir),
        "source_family": "iacs_ur",
        "measure_method": measure_method,
        "files": files_entry,
        "total_tokens": total_tokens,
        "total_files": len(files_entry),
        "by_series_count": {k: len(v) for k, v in sorted(by_series.items())},
        "additivity_errors": errors_any,
        "additivity_warnings": warnings_any,
    }

    scan_index_path = scan_dir / "scan_index.json"
    with open(scan_index_path, "w", encoding="utf-8") as f:
        json.dump(scan_index, f, ensure_ascii=False, indent=2)

    doc_parts = {
        "schema_version": 1,
        "session_id": session_id,
        "items": doc_parts_items,
    }
    doc_parts_path = parts_dir / "doc_parts.json"
    with open(doc_parts_path, "w", encoding="utf-8") as f:
        json.dump(doc_parts, f, ensure_ascii=False, indent=2)

    print(f"\n=== Phase A done ===")
    print(f"total_files: {scan_index['total_files']}")
    print(f"total_tokens: {scan_index['total_tokens']:,}")
    print(f"by_series: {scan_index['by_series_count']}")
    print(f"additivity_errors: {len(errors_any)}")
    print(f"additivity_warnings: {len(warnings_any)} (|diff|<=2, BPE boundary artifact)")
    print(f"measure_method: {measure_method}")
    print(f"Written: {scan_index_path}")
    print(f"Written: {doc_parts_path} ({len(doc_parts_items)} items)")


if __name__ == "__main__":
    main()
