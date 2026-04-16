#!/usr/bin/env python3
"""md2wu Series Coordinator — End-to-end Phase A→B→C for one UR series.

Usage:
    python coord_series.py <series_letter> <src_dir> <skill_root> [--session-id ID]

Steps per series:
  1. Acquire lock skill_root/queue/locks/iacs_ur_<s>.lock (O_CREAT|O_EXCL)
  2. Phase A: parse filename → keys → run heading_tokens per file → TSV in temp/pre/<s>/
  3. Phase B: build single batch (all series files fit ≤600K)
  4. Phase C/S5-6: chunk_wu.py
  5. Phase C/S7: manifest.py
  6. Extract WU content from source files based on WU meta
  7. Add iacs_ur_ prefix to wu/manifest/issue_gate filenames; move to skill_root
  8. Release lock
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path("/mnt/c/shared_wk/ontology_iacs/.claude/skills/md2wu")
PYTHON = "/mnt/c/shared_wk/ontology_iacs/.venv-md2wu/bin/python"


def parse_filename(filename: str):
    """Return (document_key, doc_instance_key) from a UR md filename.

    Examples:
      ur-a2rev5.md            -> ('a2', 'a2_rev5_en')
      UR-C6New.md             -> ('c6', 'c6_new_en')
      UR-D8-Rev.3-Feb-2021CLN.md -> ('d8', 'd8_rev3_en')
      ur-d11rev4corr1.md      -> ('d11', 'd11_rev4_corr1_en')
      UR-H1-Withdrawn-Nov-2024.md -> ('h1', 'h1_withdrawn_en')
      UR_P2_Oct_2023_CLN1.md  -> ('p2', 'p2_en')
      ur-s1arev6.md           -> ('s1a', 's1a_rev6_en')
      UR-S10-Rev-8-Sep-2025-CLN.md -> ('s10', 's10_rev8_en')
      ur-s20-rev6.md          -> ('s20', 's20_rev6_en')
      UR-Z10.3-Rev.21-Aug-2023-CLN.md -> ('z10_3', 'z10_3_rev21_en')
    """
    stem = filename
    if stem.endswith(".md"):
        stem = stem[:-3]
    # Strip trailing -N (e.g., -1) variant suffixes — assume max -9
    stem = re.sub(r"-\d$", "", stem)
    # Normalize: lowercase, _ → -
    stem = stem.lower().replace("_", "-")
    # Strip leading ur-
    stem = re.sub(r"^ur-+", "", stem)
    # Strip CLN/CR markers and trailing dates
    months = "(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)"
    stem = re.sub(rf"-{months}-\d{{4}}.*$", "", stem)
    stem = re.sub(r"-cln\d*$", "", stem)
    stem = re.sub(r"-cr$", "", stem)
    stem = re.sub(r"-cln-?$", "", stem)

    # Split at first keyword (rev|corr|del|new|withdrawn) wherever it appears
    keyword_re = re.compile(r"(rev|corr|del|new|withdrawn)", re.IGNORECASE)
    km = keyword_re.search(stem)
    if km:
        doc_part = stem[:km.start()].rstrip("-_")
        rev_part = stem[km.start():]
    else:
        doc_part = stem
        rev_part = ""

    # Parse doc_part: letter + digits (+ optional sub-letter) (+ optional .digits)
    m = re.match(r"^([a-z])(\d+)([a-z])?(?:\.(\d+))?$", doc_part)
    if not m:
        slug = re.sub(r"[^a-z0-9]+", "_", doc_part).strip("_")
        return slug, f"{slug}_en"

    series_letter = m.group(1)
    doc_num = m.group(2)
    sub_letter = m.group(3) or ""
    sub_num = m.group(4) or ""

    document_key = f"{series_letter}{doc_num}{sub_letter}"
    if sub_num:
        document_key += f"_{sub_num}"

    # Parse rev_part for rev/corr/del/new/withdrawn
    rev_m = re.search(r"rev[.\-]?(\d+)", rev_part)
    corr_m = re.search(r"corr[.\-]?(\d+)", rev_part)
    state_m = re.search(r"\b(del|new|withdrawn)\b", rev_part)

    parts = [document_key]
    if rev_m:
        parts.append(f"rev{rev_m.group(1)}")
    if corr_m:
        parts.append(f"corr{corr_m.group(1)}")
    if state_m and not (rev_m or corr_m):
        parts.append(state_m.group(1))
    parts.append("en")
    doc_instance_key = "_".join(parts)
    return document_key, doc_instance_key


def acquire_lock(lock_path: Path, session_id: str, state: str = "scanning"):
    payload = json.dumps({
        "owner": session_id,
        "state": state,
        "claimed_at": datetime.now(timezone.utc).isoformat(),
    })
    fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        os.write(fd, payload.encode())
    finally:
        os.close(fd)


def update_lock(lock_path: Path, session_id: str, state: str):
    tmp = lock_path.with_suffix(".lock.tmp")
    payload = json.dumps({
        "owner": session_id,
        "state": state,
        "claimed_at": datetime.now(timezone.utc).isoformat(),
    })
    tmp.write_text(payload)
    os.replace(tmp, lock_path)


def release_lock(lock_path: Path):
    try:
        os.unlink(lock_path)
    except FileNotFoundError:
        pass


def extract_wu_content(meta_path: Path, src_dir: Path, out_path: Path):
    """Extract WU content from source files based on constituent_docs ranges."""
    meta = json.loads(meta_path.read_text())
    parts = []
    for cd in meta["constituent_docs"]:
        # Find source file by doc_instance_key prefix match
        dik = cd["doc_instance_key"]
        # We need to map dik back to source filename. Build index.
        # For now, search src_dir for any .md file whose parsed key matches.
        matched = None
        for f in src_dir.glob("*.md"):
            _, this_dik = parse_filename(f.name)
            if this_dik == dik:
                matched = f
                break
        if not matched:
            parts.append(f"<!-- WARNING: source file for {dik} not found -->\n")
            continue
        lines = matched.read_text(encoding="utf-8").splitlines()
        start = cd.get("start_line", 1)
        end = cd.get("end_line", len(lines))
        # 1-based inclusive
        chunk = "\n".join(lines[start - 1: end])
        if len(meta["constituent_docs"]) > 1:
            parts.append(f"<!-- begin: {dik} (lines {start}-{end}) -->\n")
        parts.append(chunk)
        if len(meta["constituent_docs"]) > 1:
            parts.append(f"\n<!-- end: {dik} -->\n")
    out_path.write_text("\n".join(parts), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("series", help="Series letter (a, c, d, ...)")
    ap.add_argument("src_dir", help="Source directory containing UR_<S>_md")
    ap.add_argument("skill_root", help="skill_md2wu output root")
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--chunk-max", type=int, default=32000)
    ap.add_argument("--wu-min", type=int, default=16000)
    args = ap.parse_args()

    series = args.series.lower()
    src_dir = Path(args.src_dir)
    skill_root = Path(args.skill_root)
    session_id = args.session_id or datetime.now(timezone.utc).strftime("s%Y%m%d-%H%M%S")
    corpus_scope = f"iacs_ur_{series}"

    # Setup paths
    locks_dir = skill_root / "queue" / "locks"
    sessions_dir = skill_root / "queue" / "sessions" / session_id
    temp_dir = skill_root / "temp" / "pre" / series
    locks_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    skill_root.mkdir(parents=True, exist_ok=True)

    lock_path = locks_dir / f"{corpus_scope}.lock"

    # 1. Acquire lock
    try:
        acquire_lock(lock_path, session_id, "scanning")
    except FileExistsError:
        existing = lock_path.read_text()
        print(f"LOCK_HELD {corpus_scope}: {existing}", file=sys.stderr)
        sys.exit(2)

    try:
        # 2. Phase A: heading_tokens per file
        files = sorted(src_dir.glob("*.md"))
        if not files:
            print(f"NO_FILES in {src_dir}", file=sys.stderr)
            release_lock(lock_path)
            return

        scan_results = []
        for f in files:
            doc_key, dik = parse_filename(f.name)
            try:
                r = subprocess.run(
                    [PYTHON, str(SKILL_DIR / "heading_tokens.py"),
                     str(f), dik, doc_key, str(temp_dir)],
                    capture_output=True, text=True, check=True
                )
            except subprocess.CalledProcessError as e:
                print(f"HEADING_TOKENS_FAIL {f.name}: {e.stderr}", file=sys.stderr)
                continue
            tsv_path = temp_dir / f"doc-{dik}__heading__structure.tsv"
            scan_results.append({
                "filename": f.name,
                "doc_instance_key": dik,
                "document_key": doc_key,
                "tsv_path": str(tsv_path),
                "src_path": str(f),
            })
            print(f"  scanned: {dik}")

        # Write scan_index for this series
        scan_index = {
            "scan_id": datetime.now(timezone.utc).isoformat(),
            "series": series,
            "corpus_scope": corpus_scope,
            "source_dir": str(src_dir),
            "files": scan_results,
            "total_files": len(scan_results),
        }
        scan_idx_path = sessions_dir / f"scan_index_{series}.json"
        scan_idx_path.write_text(json.dumps(scan_index, indent=2, ensure_ascii=False))

        # 3-4. Phase B/C: chunk_wu
        update_lock(lock_path, session_id, "processing")
        r = subprocess.run(
            [PYTHON, str(SKILL_DIR / "chunk_wu.py"),
             str(temp_dir),
             "--chunk-max", str(args.chunk_max),
             "--wu-min", str(args.wu_min),
             "--authority", "IACS",
             "--doc-type", "UR",
             "--grammar-version", "iacs_ur_v01"],
            capture_output=True, text=True, check=True
        )
        print(r.stdout)

        # 5. Phase C/S7: manifest
        r = subprocess.run(
            [PYTHON, str(SKILL_DIR / "manifest.py"),
             str(temp_dir),
             "--chunk-max", str(args.chunk_max),
             "--source-dir", str(src_dir),
             "--source-family", f"IACS UR {series.upper()}",
             "--authority", "IACS",
             "--doc-type", "UR"],
            capture_output=True, text=True, check=True
        )
        print(r.stdout)

        # 6. Extract WU content; rename with iacs_ur_ prefix; move to skill_root
        for meta_file in sorted(temp_dir.glob("wu-*__pre__meta.json")):
            wu_key_raw = meta_file.name[len("wu-"):-len("__pre__meta.json")]
            new_wu_key = f"iacs_ur_{wu_key_raw}"

            # Update meta with prefixed key
            meta = json.loads(meta_file.read_text())
            meta["wu_key"] = new_wu_key
            meta["corpus_scope"] = corpus_scope

            new_meta_name = f"wu-{new_wu_key}__pre__meta.json"
            new_content_name = f"wu-{new_wu_key}__pre__content.md"

            # Extract content
            content_path = skill_root / new_content_name
            extract_wu_content(meta_file, src_dir, content_path)
            meta["output_files"] = [new_content_name]
            (skill_root / new_meta_name).write_text(
                json.dumps(meta, indent=2, ensure_ascii=False)
            )

        # 7. Rename manifest + issue_gate with corpus prefix
        manifest_src = temp_dir / "corpus__pre__manifest.json"
        if manifest_src.exists():
            manifest = json.loads(manifest_src.read_text())
            # Update wu_keys with prefix
            for w in manifest.get("work_units", []):
                w["wu_key"] = f"iacs_ur_{w['wu_key']}"
                w["meta_file"] = f"wu-iacs_ur_{w['wu_key'][len('iacs_ur_'):]}__pre__meta.json"
            manifest["corpus_scope"] = corpus_scope
            (skill_root / f"corpus-{corpus_scope}__pre__manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False)
            )

        issue_src = temp_dir / "corpus__md2wu__issue_gate_report.json"
        if issue_src.exists():
            issue = json.loads(issue_src.read_text())
            for it in issue.get("issues", []):
                it["wu_key"] = f"iacs_ur_{it['wu_key']}"
            (skill_root / f"corpus-{corpus_scope}__md2wu__issue_gate_report.json").write_text(
                json.dumps(issue, indent=2, ensure_ascii=False)
            )

        update_lock(lock_path, session_id, "done")
        release_lock(lock_path)
        print(f"DONE {corpus_scope}: {len(scan_results)} files processed")

    except Exception as e:
        update_lock(lock_path, session_id, "failed")
        print(f"FAILED {corpus_scope}: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
