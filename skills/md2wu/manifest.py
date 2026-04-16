#!/usr/bin/env python3
"""md2wu Stage 7: Issue gate + Manifest generation.

Usage:
    python manifest.py <tsv_dir> [--chunk-max 32000]

Reads all wu-*__pre__meta.json files, checks issue triggers,
updates WU status, and generates corpus__pre__manifest.json.
"""

import json
import os
import sys
from datetime import datetime, timezone


def main():
    import argparse
    p = argparse.ArgumentParser(description="Stage 7: Issue gate + Manifest")
    p.add_argument("tsv_dir", help="Directory containing WU meta files")
    p.add_argument("--chunk-max", type=int, default=32000)
    p.add_argument("--source-dir", default="", help="Source directory path for manifest")
    p.add_argument("--source-family", default="IACS UR/UI/Rec/PR")
    p.add_argument("--authority", default="IACS")
    p.add_argument("--doc-type", default="UR")
    args = p.parse_args()

    tsv_dir = args.tsv_dir
    chunk_max = args.chunk_max
    chunk_exception = int(chunk_max * 1.5)
    now = datetime.now(timezone.utc).isoformat()

    wu_files = sorted(f for f in os.listdir(tsv_dir) if f.startswith("wu-") and f.endswith("__pre__meta.json"))
    wus = []
    for f in wu_files:
        with open(os.path.join(tsv_dir, f)) as fp:
            wus.append(json.load(fp))

    # Issue gate
    issues = []
    for wu in wus:
        tokens = wu["est_tokens_total"]
        if tokens > chunk_exception:
            issues.append({"wu_key": wu["wu_key"], "type": "oversize_hard", "severity": "HIGH", "tokens": tokens})
        elif tokens > chunk_max:
            issues.append({"wu_key": wu["wu_key"], "type": "oversize_exception", "severity": "INFO", "tokens": tokens})
        if wu["wu_type"] in ("split", "standalone") and tokens < chunk_max // 2:
            issues.append({"wu_key": wu["wu_key"], "type": "undersized", "severity": "LOW", "tokens": tokens})

    if issues:
        report = {"issues": issues, "created_at": now}
        with open(os.path.join(tsv_dir, "corpus__md2wu__issue_gate_report.json"), "w") as fp:
            json.dump(report, fp, indent=2)
        print("Issues:")
        for iss in issues:
            print(f"  [{iss['severity']}] {iss['wu_key']}: {iss['type']} ({iss['tokens']:,} tokens)")
    else:
        print("No issues triggered.")

    # Update all WU status to processed (auto-proceed for INFO)
    high_issues = [i for i in issues if i["severity"] == "HIGH"]
    for wu in wus:
        if any(i["wu_key"] == wu["wu_key"] for i in high_issues):
            wu["status"] = "planned"  # Keep as planned for HIGH — needs user decision
        else:
            wu["status"] = "processed"
        with open(os.path.join(tsv_dir, f"wu-{wu['wu_key']}__pre__meta.json"), "w") as fp:
            json.dump(wu, fp, indent=2, ensure_ascii=False)

    # Count documents
    doc_keys = set()
    for wu in wus:
        for cd in wu["constituent_docs"]:
            doc_keys.add(cd["doc_instance_key"])

    # Manifest
    manifest = {
        "manifest_version": "1.0",
        "created_at": now,
        "source_directory": args.source_dir,
        "source_family": args.source_family,
        "authority": args.authority,
        "doc_type": args.doc_type,
        "language": "en",
        "document_count": len(doc_keys),
        "total_tokens": sum(wu["est_tokens_total"] for wu in wus),
        "wu_summary": {
            "total": len(wus),
            "split": len([w for w in wus if w["wu_type"] == "split"]),
            "standalone": len([w for w in wus if w["wu_type"] == "standalone"]),
            "merged": len([w for w in wus if w["wu_type"] == "merged"]),
        },
        "work_units": [{
            "wu_key": wu["wu_key"],
            "wu_type": wu["wu_type"],
            "est_tokens_total": wu["est_tokens_total"],
            "status": wu["status"],
            "constituent_doc_count": len(wu["constituent_docs"]),
            "chunk_count": len(wu["chunk_keys"]),
            "meta_file": f"wu-{wu['wu_key']}__pre__meta.json",
        } for wu in wus],
    }

    manifest_path = os.path.join(tsv_dir, "corpus__pre__manifest.json")
    with open(manifest_path, "w") as fp:
        json.dump(manifest, fp, indent=2, ensure_ascii=False)

    print(f"\nManifest: {manifest_path}")
    print(f"  Documents: {len(doc_keys)}, WUs: {len(wus)}, Tokens: {manifest['total_tokens']:,}")
    if high_issues:
        print(f"\n  WARNING: {len(high_issues)} HIGH issues need user decision before proceeding.")


if __name__ == "__main__":
    main()
