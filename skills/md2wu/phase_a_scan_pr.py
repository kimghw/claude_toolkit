#!/usr/bin/env python3
"""Phase A orchestrator for IACS PR — walk PR/PR_*_md/ and run heading_tokens.

Usage: phase_a_scan_pr.py <source_dir> <session_id>

Writes:
  queue/sessions/<session_id>/scan/scan_index.json
  queue/sessions/<session_id>/parts/doc_parts.json   (single consolidated file,
                                                       items[<item_id>].headings)
"""

import json
import re
import sys
import datetime as dt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heading_tokens as ht


WORKROOT = Path("/home/kimghw/ontology_iacs/skill_md2wu")
SOURCE_FAMILY = "iacs_pr"

MONTH_MAP = {
    "jan": "01", "january": "01",
    "feb": "02", "february": "02",
    "mar": "03", "march": "03",
    "apr": "04", "april": "04",
    "may": "05",
    "jun": "06", "june": "06",
    "jul": "07", "july": "07",
    "aug": "08", "august": "08",
    "sep": "09", "sept": "09", "september": "09",
    "oct": "10", "october": "10",
    "nov": "11", "november": "11",
    "dec": "12", "december": "12",
}

PREAMBLE_REV_RE = re.compile(r'\(\s*Rev\.?\s*(\d+)[^)]*\)', re.IGNORECASE)
PREAMBLE_CORR_RE = re.compile(r'\(\s*Corr\.?\s*(\d+)[^)]*\)', re.IGNORECASE)
PREAMBLE_WITHDRAWN_RE = re.compile(r'\(\s*Withdrawn[^)]*\)', re.IGNORECASE)
BODY_DELETED_RE = re.compile(r'^\s*Deleted\b', re.IGNORECASE)
BODY_WITHDRAWN_RE = re.compile(r'^\s*Withdrawn\b', re.IGNORECASE)


def scan_preamble(lines, max_lines=25):
    """Scan up to max_lines (after the first L1) for rev/corr/del markers.

    Returns dict {revision, corr, is_del}. Picks the MAX rev number seen.
    """
    result = {"revision": None, "corr": None, "is_del": False}
    # Find first L1 heading line index
    l1_idx = None
    for i, line in enumerate(lines):
        if re.match(r'^#\s+', line):
            l1_idx = i
            break
    start = (l1_idx + 1) if l1_idx is not None else 0
    end = min(start + max_lines, len(lines))

    revs = []
    corrs = []
    for i in range(start, end):
        line = lines[i]
        for m in PREAMBLE_REV_RE.finditer(line):
            try:
                revs.append(int(m.group(1)))
            except ValueError:
                pass
        for m in PREAMBLE_CORR_RE.finditer(line):
            try:
                corrs.append(int(m.group(1)))
            except ValueError:
                pass
        if PREAMBLE_WITHDRAWN_RE.search(line):
            result["is_del"] = True
        if BODY_DELETED_RE.match(line) or BODY_WITHDRAWN_RE.match(line):
            result["is_del"] = True

    if revs:
        result["revision"] = str(max(revs))
    if corrs:
        result["corr"] = str(max(corrs))
    return result


def month_to_num(month_token: str) -> str | None:
    key = month_token.lower().rstrip('.')
    return MONTH_MAP.get(key)


def extract_date_yyyymm(stem: str) -> str | None:
    """Find <Month>-<YYYY> pattern in filename stem and return YYYYMM."""
    low = stem.lower()
    m = re.search(r'\b([a-z]+)[-_\.\s]*(20\d{2})\b', low)
    if not m:
        return None
    month_token = m.group(1)
    year = m.group(2)
    num = month_to_num(month_token)
    if not num:
        return None
    return f"{year}{num}"


def parse_pr_filename(stem: str, lines: list[str]) -> dict | None:
    """Extract item_id tail and metadata from PR filename.

    Handles: contact, annex, addendum, pdf-extract, standard rev/corr/del variants.
    Returns None if file is not parseable.
    """
    low = stem.lower()
    # Normalise separators
    norm = re.sub(r'\s+', '-', low)

    # --- 1. Contact details ---------------------------------------------------
    if "contact" in norm:
        # First PR number reference wins
        nums = re.findall(r'pr[-_\.\s]*(\d+[a-z]?)', norm)
        if not nums:
            return None
        first_num = nums[0]
        yyyymm = extract_date_yyyymm(stem) or "unknown"
        tail = f"pr{first_num}_contact_{yyyymm}_en"
        # Date-based order key so multiple contact docs sort stably
        order_primary = 0
        # Extract leading digits for ordering
        digits_m = re.match(r'(\d+)', first_num)
        order_primary = int(digits_m.group(1)) if digits_m else 0
        return {
            "tail": tail,
            "series_key": "pr",
            "series_order": [order_primary, 9000, 0, 0],
            "revision": None,
            "corr": None,
            "is_del": False,
            "variant": "contact",
            "related_prs": nums,
            "date": yyyymm,
        }

    # Strip leading "pr-", "pr_", "pr" to expose number.
    # Only accept a single-letter suffix from {a,b,c,d} (IACS PR convention: PR1A/1B/1C/1D, PR2A/2B, PR10B).
    # Crucially, the suffix letter must be followed by a delimiter OR a known
    # marker word (rev|corr|add|annex|del|withdrawn) — otherwise it's part of
    # that marker's leading letter (e.g. "6rev4": 'r' is not a suffix).
    stripped = norm
    m = re.match(
        r'^pr[-_\.]?(\d+)([abcd])?(?=[-_\.]|rev|corr|add|annex|del|withdrawn|$)(.*)$',
        stripped,
    )
    if not m:
        return None
    num_digits_raw = m.group(1)
    num_letter = m.group(2) or ""
    rest = m.group(3)
    # Strip leading zeros from digits (e.g. "02" → "2")
    num_digits = str(int(num_digits_raw))
    num_under = num_digits + num_letter  # e.g. "1b", "10b", "42", "2"

    # --- 2. Detect variant markers in rest ------------------------------------
    # Variant markers (annex / add / del) must appear as the FIRST token after
    # the PR number. "-with-annex-1" later in the filename (e.g. PR-1B) is a
    # cross-reference, not a variant flag.
    is_annex = bool(re.match(r'^[-_\.]annex(?:[-_\.]|$)', rest))
    is_add = bool(re.match(r'^[-_\.]add(?:endum)?(?:[-_\.]|$)', rest))
    is_del_filename = bool(re.match(r'^[-_\.]del(?:[-_\.]|$)', rest))
    is_withdrawn_filename = bool(re.search(r'withdrawn', rest))
    # pdf-extracted file: contains "_pdf<digits>" (no rev in filename)
    is_pdf_extract = bool(re.search(r'[-_]pdf\d+$', rest))

    rev_m = re.search(r'rev[\.\-_]?(\d+)', rest, re.IGNORECASE)
    corr_m = re.search(r'corr[\.\-_]?(\d+)', rest, re.IGNORECASE)
    revision = rev_m.group(1) if rev_m else None
    corr = corr_m.group(1) if corr_m else None

    # --- 3. For pdf-extract files, scan body preamble -------------------------
    body = scan_preamble(lines) if is_pdf_extract or not revision else None
    if is_pdf_extract and body:
        revision = revision or body["revision"]
        corr = corr or body["corr"]

    # --- 4. is_del final decision ---------------------------------------------
    is_del = is_del_filename or is_withdrawn_filename
    if not is_del:
        # Also check body preamble for "Deleted" / "Withdrawn"
        if body is None:
            body = scan_preamble(lines)
        if body["is_del"]:
            is_del = True

    # --- 5. Build item_id tail ------------------------------------------------
    tail_core = f"pr{num_under}"
    if is_annex:
        tail_core += "_annex"
    elif is_add:
        tail_core += "_add"

    variant = "standard"
    if is_annex:
        variant = "annex"
    elif is_add:
        variant = "addendum"
    elif is_pdf_extract:
        variant = "pdf_extract"

    suffix_parts = []
    if revision:
        suffix_parts.append(f"rev{revision}")
    if corr:
        suffix_parts.append(f"corr{corr}")
    if is_del and not suffix_parts:
        suffix_parts.append("del")
    elif is_del:
        suffix_parts.append("del")

    tail = tail_core
    if suffix_parts:
        tail += "_" + "_".join(suffix_parts)
    tail += "_en"

    # series_order: digits of num, letter as ASCII offset, annex/add bump
    letter_ord = (ord(num_letter) - ord('a') + 1) if num_letter else 0
    variant_bump = 500 if is_annex else (400 if is_add else 0)
    order_list = [int(num_digits), letter_ord, variant_bump, int(revision) if revision else 0]

    series_key = "pr_del" if is_del else "pr"

    return {
        "tail": tail,
        "series_key": series_key,
        "series_order": order_list,
        "revision": revision,
        "corr": corr,
        "is_del": is_del,
        "variant": variant,
        "related_prs": [num_under],
    }


def main():
    source_dir = Path(sys.argv[1]).resolve()
    session_id = sys.argv[2]

    scan_dir = WORKROOT / "queue" / "sessions" / session_id / "scan"
    parts_dir = WORKROOT / "queue" / "sessions" / session_id / "parts"
    scan_dir.mkdir(parents=True, exist_ok=True)
    parts_dir.mkdir(parents=True, exist_ok=True)

    encode_fn, measure_method = ht.get_encoder()

    md_files = sorted(source_dir.glob("PR_*_md/*.md"))
    print(f"Found {len(md_files)} MD files under {source_dir}")

    files_entry = []
    total_tokens = 0
    by_series = {}
    errors_any = []
    warnings_any = []
    doc_parts_items = {}
    skipped_unparseable = []
    seen_item_ids: dict[str, str] = {}
    duplicates = []
    judgments = []  # Variant/revision inference notes

    for md_file in md_files:
        with open(md_file, "r", encoding="utf-8", errors="replace") as f:
            raw_lines = f.readlines()
        lines = [l.rstrip("\n") for l in raw_lines]
        total_lines = len(lines)

        parsed = parse_pr_filename(md_file.stem, lines)
        if parsed is None:
            skipped_unparseable.append(f"{md_file.parent.name}/{md_file.name} (unparseable)")
            continue

        tail = parsed["tail"]
        item_id = f"iacs_pr_{tail}"
        # document_key: strip rev/corr/del suffixes from tail
        doc_tail = re.sub(r'_(rev\d+|corr\d+|del)(?=_|$)', '', tail)
        doc_tail = re.sub(r'__+', '_', doc_tail)
        document_key = f"iacs_pr_{doc_tail}"

        if item_id in seen_item_ids:
            duplicates.append({
                "item_id": item_id,
                "kept": seen_item_ids[item_id],
                "dropped": str(md_file),
            })
            continue
        seen_item_ids[item_id] = str(md_file)

        # Record judgment for pdf-extract variants (revision inferred from body)
        if parsed["variant"] == "pdf_extract":
            judgments.append({
                "stage": "S1",
                "severity": "MED" if parsed["revision"] else "LOW",
                "category": "revision_extraction",
                "target": md_file.name,
                "ambiguity": "pdf-auto-extract 파일명에 revision 정보 없음",
                "decision": f"body preamble 스캔 → revision={parsed['revision']}, corr={parsed['corr']}, is_del={parsed['is_del']}",
                "risk": "body preamble이 개정 이력을 누락하면 revision 미식별 → item_id 충돌·분류 오류 가능",
            })
        if parsed["variant"] == "contact":
            judgments.append({
                "stage": "S1",
                "severity": "LOW",
                "category": "item_id_extraction",
                "target": md_file.name,
                "ambiguity": "Contact 문서가 여러 PR을 공용으로 참조",
                "decision": f"첫 번째 PR 번호 기준 item_id={item_id}, related_prs={parsed['related_prs']}",
                "risk": "다른 PR에서 역참조 시 item_id 추적 필요",
            })

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
        by_series.setdefault(parsed["series_key"], []).append(item_id)

        files_entry.append({
            "item_id": item_id,
            "document_key": document_key,
            "filepath": str(md_file),
            "cost_tokens": cost_tokens,
            "heading_count": len(headings),
            "source_family": SOURCE_FAMILY,
            "series": parsed["series_key"],
            "series_order": list(parsed["series_order"]),
            "revision": parsed["revision"],
            "corr": parsed["corr"],
            "is_del": parsed["is_del"],
            "variant": parsed["variant"],
            "related_prs": parsed.get("related_prs", []),
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
        "judgments": judgments,
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

    print("\n=== Phase A (PR) done ===")
    print(f"total_files: {scan_index['total_files']}")
    print(f"total_tokens: {scan_index['total_tokens']:,}")
    print(f"by_series: {scan_index['by_series_count']}")
    print(f"additivity_errors: {len(errors_any)}")
    print(f"additivity_warnings: {len(warnings_any)}")
    print(f"skipped_unparseable: {len(skipped_unparseable)}")
    for s in skipped_unparseable[:10]:
        print(f"  - {s}")
    print(f"duplicates: {len(duplicates)}")
    for d in duplicates[:10]:
        print(f"  - {d['item_id']}: kept={Path(d['kept']).name}, dropped={Path(d['dropped']).name}")
    print(f"judgments: {len(judgments)}")
    print(f"measure_method: {measure_method}")
    print(f"Written: {scan_index_path}")
    print(f"Written: {doc_parts_path} ({len(doc_parts_items)} items)")


if __name__ == "__main__":
    main()
