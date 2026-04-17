#!/usr/bin/env python3
"""Phase A orchestrator for IACS UI — walk UI/UI_*_md/ and run heading_tokens.

Usage: phase_a_scan_ui.py <source_dir> <session_id>

Writes:
  queue/sessions/<session_id>/scan/scan_index.json
  queue/sessions/<session_id>/parts/doc_parts.json   (single consolidated file,
                                                       items[<item_id>].headings)
"""

import json
import os
import re
import sys
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heading_tokens as ht


WORKROOT = Path("/home/kimghw/ontology_iacs/skill_md2wu")
SOURCE_FAMILY = "iacs_ui"

# Series short codes recognized under UI_<CODE>_md/ subdirs.
UI_SERIES_SHORTS = {"cc", "colreg", "ftp", "gc", "gf", "hsc", "ll",
                    "modu", "mpc", "passub", "sc", "tm"}

REV_RE = re.compile(r'rev[_\-\.]?(\d+)', re.IGNORECASE)
CORR_RE = re.compile(r'corr[_\-\.]?(\d+)', re.IGNORECASE)
DEL_RE = re.compile(r'\b(?:del|withdrawn|deleted)\b', re.IGNORECASE)


def parse_ui_filename(stem: str, series_short: str):
    """Extract (num_underscore, revision, corr, is_del, series_order, item_id_tail).

    series_short is the lowercase code from the parent dir (cc, sc, mpc, ...).
    The function strips known prefixes (ui-, ui_, hsc-code, series_short) then
    parses the leading digit group and tail for rev/corr/del/withdrawn markers.
    Returns None if no numeric group is found.
    """
    low = stem.lower()

    # Candidate prefixes to strip, ordered by specificity.
    prefixes = [
        f"ui-{series_short}",
        f"ui_{series_short}",
        f"ui{series_short}",
    ]
    # HSC-specific extra prefix
    if series_short == "hsc":
        prefixes.append("hsc-code")
        prefixes.append("hsccode")
    prefixes.append(series_short)

    stripped = low
    for p in prefixes:
        if stripped.startswith(p):
            stripped = stripped[len(p):]
            break

    # Allow an optional leading delimiter before the number.
    stripped = re.sub(r'^[\-_.]+', '', stripped)

    m = re.match(r'^(\d+(?:[\-_.]\d+)*)(.*)$', stripped)
    if not m:
        return None
    num_str = m.group(1)
    rest = m.group(2)

    # Normalize number into underscore form.
    num_under = re.sub(r'[\-.]', '_', num_str)

    rev_m = REV_RE.search(rest)
    corr_m = CORR_RE.search(rest)
    revision = rev_m.group(1) if rev_m else None
    corr = corr_m.group(1) if corr_m else None
    is_del = bool(DEL_RE.search(rest))

    # series_order: tuple of ints from num_under.
    nums = [int(x) for x in num_under.split("_") if x.isdigit()]
    while len(nums) < 4:
        nums.append(0)
    series_order = tuple(nums)

    # Build item_id tail: {series_short}{num_under}[_rev{N}][_corr{N}][_del]_en
    tail = f"{series_short}{num_under}"
    if revision:
        tail += f"_rev{revision}"
    if corr:
        tail += f"_corr{corr}"
    if is_del and not revision and not corr:
        tail += "_del"
    elif is_del:
        tail += "_del"
    tail += "_en"

    return {
        "num_under": num_under,
        "revision": revision,
        "corr": corr,
        "is_del": is_del,
        "series_order": series_order,
        "item_id_tail": tail,
    }


def series_short_from_parent(parent_name: str) -> str | None:
    """Extract series short code from parent dir name 'UI_<CODE>_md'."""
    m = re.match(r'^UI_([A-Za-z]+)_md$', parent_name)
    if not m:
        return None
    code = m.group(1).lower()
    if code not in UI_SERIES_SHORTS:
        return None
    return code


def main():
    source_dir = Path(sys.argv[1]).resolve()
    session_id = sys.argv[2]

    scan_dir = WORKROOT / "queue" / "sessions" / session_id / "scan"
    parts_dir = WORKROOT / "queue" / "sessions" / session_id / "parts"
    scan_dir.mkdir(parents=True, exist_ok=True)
    parts_dir.mkdir(parents=True, exist_ok=True)

    encode_fn, measure_method = ht.get_encoder()

    md_files = sorted(source_dir.glob("UI_*_md/*.md"))
    print(f"Found {len(md_files)} MD files under {source_dir}")

    files_entry = []
    total_tokens = 0
    by_series = {}
    errors_any = []
    warnings_any = []
    doc_parts_items = {}
    skipped_unparseable = []
    seen_item_ids: dict[str, str] = {}  # item_id -> filepath already processed
    duplicates = []

    for md_file in md_files:
        parent = md_file.parent.name
        series_short = series_short_from_parent(parent)
        if series_short is None:
            skipped_unparseable.append(f"{parent}/{md_file.name} (unknown parent)")
            continue

        parsed = parse_ui_filename(md_file.stem, series_short)
        if parsed is None:
            skipped_unparseable.append(f"{parent}/{md_file.name} (no number)")
            continue

        tail = parsed["item_id_tail"]
        item_id = f"iacs_ui_{tail}"
        # document_key: same as item_id but without rev/corr/del suffixes (logical key)
        # Simpler: iacs_ui_{series_short}{num_under}
        document_key = f"iacs_ui_{series_short}{parsed['num_under']}"

        if item_id in seen_item_ids:
            duplicates.append({
                "item_id": item_id,
                "kept": seen_item_ids[item_id],
                "dropped": str(md_file),
            })
            continue
        seen_item_ids[item_id] = str(md_file)

        series_key = f"ui_{series_short}_del" if parsed["is_del"] else f"ui_{series_short}"

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
        by_series.setdefault(series_key, []).append(item_id)

        files_entry.append({
            "item_id": item_id,
            "document_key": document_key,
            "filepath": str(md_file),
            "cost_tokens": cost_tokens,
            "heading_count": len(headings),
            "source_family": SOURCE_FAMILY,
            "series": series_key,
            "series_order": list(parsed["series_order"]),
            "revision": parsed["revision"],
            "corr": parsed["corr"],
            "is_del": parsed["is_del"],
        })

    files_entry.sort(key=lambda e: (e["series"], tuple(e["series_order"]), e["item_id"]))

    scan_index = {
        "scan_id": dt.datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        "source_dir": str(source_dir),
        "source_family": SOURCE_FAMILY,
        "measure_method": measure_method,
        "files": files_entry,
        "total_tokens": total_tokens,
        "total_files": len(files_entry),
        "by_series_count": {k: len(v) for k, v in sorted(by_series.items())},
        "additivity_errors": errors_any,
        "additivity_warnings": warnings_any,
        "skipped_unparseable": skipped_unparseable,
        "duplicates": duplicates,
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

    print("\n=== Phase A (UI) done ===")
    print(f"total_files: {scan_index['total_files']}")
    print(f"total_tokens: {scan_index['total_tokens']:,}")
    print(f"by_series: {scan_index['by_series_count']}")
    print(f"additivity_errors: {len(errors_any)}")
    print(f"additivity_warnings: {len(warnings_any)} (|diff|<=2, BPE boundary artifact)")
    print(f"skipped_unparseable: {len(skipped_unparseable)}")
    for s in skipped_unparseable[:10]:
        print(f"  - {s}")
    print(f"measure_method: {measure_method}")
    print(f"Written: {scan_index_path}")
    print(f"Written: {doc_parts_path} ({len(doc_parts_items)} items)")


if __name__ == "__main__":
    main()
