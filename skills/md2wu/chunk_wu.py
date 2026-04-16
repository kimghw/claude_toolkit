#!/usr/bin/env python3
"""md2wu Stage 5-6: Chunk planning + Work Unit packing.

Usage:
    python chunk_wu.py <tsv_dir> [--chunk-max 32000] [--wu-min 16000]

Reads all doc-*__heading__structure.tsv files from <tsv_dir>,
generates chunk plans and WU meta files.

Output:
    doc-{key}__heading__chunk_plan.json  (per document)
    wu-{wu_key}__pre__meta.json         (per WU)
"""

import json
import os
import sys
import hashlib
from datetime import datetime, timezone


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Stage 5-6: Chunk + WU packing")
    p.add_argument("tsv_dir", help="Directory containing heading structure TSVs")
    p.add_argument("--chunk-max", type=int, default=32000, help="Chunk max tokens (default: 32000)")
    p.add_argument("--chunk-exception", type=int, default=None, help="Exception threshold (default: 1.5x chunk-max)")
    p.add_argument("--wu-min", type=int, default=16000, help="WU lower bound (default: 16000)")
    p.add_argument("--authority", default="IACS", help="Authority (default: IACS)")
    p.add_argument("--doc-type", default="UR", help="DocType (default: UR)")
    p.add_argument("--grammar-version", default="iacs_ur_z_v01", help="Grammar version")
    return p.parse_args()


def parse_tsv(filepath):
    headings = []
    with open(filepath) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("Heading_ID"):
                continue
            parts = line.split("\t")
            if len(parts) >= 8:
                headings.append({
                    "heading_id": parts[0],
                    "level": int(parts[1]),
                    "start_line": int(parts[2]),
                    "end_line": int(parts[3]),
                    "title": parts[4],
                    "parent_id": parts[5],
                    "est_tokens_inclusive": int(parts[6]),
                    "est_tokens_exclusive": int(parts[7]),
                })
    return headings


def create_chunk_plan(doc_key, headings, total_tokens, chunk_max, chunk_exception, wu_min):
    chunks = []
    if total_tokens == 0 or not headings:
        return chunks

    # Single chunk cases
    if total_tokens <= chunk_exception:
        chunks.append({
            "chunk_key": f"{doc_key}_ch001",
            "heading_range": {"first": headings[0]["heading_id"], "last": headings[-1]["heading_id"]},
            "heading_level": "Document",
            "start_line": headings[0]["start_line"],
            "end_line": headings[-1]["end_line"],
            "est_tokens": total_tokens,
            "split_method": "recursive",
            "measure_method": "tiktoken",
            "sub_chunks": None,
        })
        return chunks

    # Split at L2 boundaries
    l2_spans = [h for h in headings if h["level"] == 2]
    l1 = next((h for h in headings if h["level"] == 1), None)

    if not l2_spans:
        chunks.append({
            "chunk_key": f"{doc_key}_ch001",
            "heading_range": {"first": headings[0]["heading_id"], "last": headings[-1]["heading_id"]},
            "heading_level": "Document",
            "start_line": headings[0]["start_line"],
            "end_line": headings[-1]["end_line"],
            "est_tokens": total_tokens,
            "split_method": "recursive",
            "measure_method": "tiktoken",
            "sub_chunks": None,
        })
        return chunks

    n_chunks = max(2, -(-total_tokens // chunk_max))
    target_tokens = total_tokens // n_chunks

    current_spans = []
    current_tokens = l1["est_tokens_exclusive"] if l1 else 0
    chunk_idx = 1

    for i, l2 in enumerate(l2_spans):
        span_tokens = l2["est_tokens_inclusive"]
        if current_tokens + span_tokens > target_tokens and current_spans and i < len(l2_spans) - 1:
            first_span = current_spans[0]
            last_span = current_spans[-1]
            chunks.append({
                "chunk_key": f"{doc_key}_ch{chunk_idx:03d}",
                "heading_range": {"first": first_span["heading_id"], "last": last_span["heading_id"]},
                "heading_level": "Section",
                "start_line": first_span["start_line"] if chunk_idx > 1 else headings[0]["start_line"],
                "end_line": last_span["end_line"],
                "est_tokens": current_tokens,
                "split_method": "recursive",
                "measure_method": "tiktoken",
                "sub_chunks": None,
            })
            chunk_idx += 1
            current_spans = [l2]
            current_tokens = span_tokens
        else:
            current_spans.append(l2)
            current_tokens += span_tokens

    if current_spans:
        chunks.append({
            "chunk_key": f"{doc_key}_ch{chunk_idx:03d}",
            "heading_range": {"first": current_spans[0]["heading_id"], "last": current_spans[-1]["heading_id"]},
            "heading_level": "Section",
            "start_line": current_spans[0]["start_line"] if chunk_idx > 1 else headings[0]["start_line"],
            "end_line": current_spans[-1]["end_line"],
            "est_tokens": current_tokens,
            "split_method": "recursive",
            "measure_method": "tiktoken",
            "sub_chunks": None,
        })

    # Merge small chunks
    merged = []
    for c in chunks:
        if merged and merged[-1]["est_tokens"] < wu_min:
            merged[-1]["end_line"] = c["end_line"]
            merged[-1]["est_tokens"] += c["est_tokens"]
            merged[-1]["heading_range"]["last"] = c["heading_range"]["last"]
        else:
            merged.append(c)

    if len(merged) > 1 and merged[-1]["est_tokens"] < wu_min:
        merged[-2]["end_line"] = merged[-1]["end_line"]
        merged[-2]["est_tokens"] += merged[-1]["est_tokens"]
        merged[-2]["heading_range"]["last"] = merged[-1]["heading_range"]["last"]
        merged.pop()

    for i, c in enumerate(merged):
        c["chunk_key"] = f"{doc_key}_ch{i + 1:03d}"

    return merged


def main():
    args = parse_args()
    tsv_dir = args.tsv_dir
    chunk_max = args.chunk_max
    chunk_exception = args.chunk_exception or int(chunk_max * 1.5)
    wu_min = args.wu_min
    now = datetime.now(timezone.utc).isoformat()

    files = sorted(f for f in os.listdir(tsv_dir) if f.endswith("__heading__structure.tsv"))
    if not files:
        print(f"No TSV files found in {tsv_dir}")
        sys.exit(1)

    all_plans = {}
    doc_summaries = []

    for f in files:
        doc_instance_key = f.replace("doc-", "").replace("__heading__structure.tsv", "")
        doc_key = "_".join(doc_instance_key.split("_")[:-2])

        headings = parse_tsv(os.path.join(tsv_dir, f))
        total_tokens = headings[0]["est_tokens_inclusive"] if headings else 0

        chunks = create_chunk_plan(doc_instance_key, headings, total_tokens, chunk_max, chunk_exception, wu_min)

        plan_path = os.path.join(tsv_dir, f"doc-{doc_instance_key}__heading__chunk_plan.json")
        with open(plan_path, "w") as fp:
            json.dump(chunks, fp, indent=2, ensure_ascii=False)

        all_plans[doc_instance_key] = chunks
        doc_summaries.append({
            "doc_instance_key": doc_instance_key,
            "doc_key": doc_key,
            "total_tokens": total_tokens,
            "chunk_count": len(chunks),
        })

    # Categorize for WU packing
    split_docs = [s for s in doc_summaries if s["total_tokens"] > chunk_exception]
    standalone_docs = [s for s in doc_summaries if wu_min <= s["total_tokens"] <= chunk_exception]
    merge_cands = [s for s in doc_summaries if s["total_tokens"] < wu_min]

    wu_count = 0

    # Split WUs
    for s in split_docs:
        for i, chunk in enumerate(all_plans[s["doc_instance_key"]]):
            wu_key = f"{s['doc_instance_key']}_wu{i + 1:03d}"
            meta = {
                "wu_key": wu_key, "wu_type": "split",
                "authority": args.authority, "doc_type": args.doc_type,
                "language": "en", "grammar_version": args.grammar_version,
                "measure_method": "tiktoken",
                "constituent_docs": [{
                    "doc_instance_key": s["doc_instance_key"],
                    "document_key": s["doc_key"],
                    "start_line": chunk["start_line"], "end_line": chunk["end_line"],
                    "est_tokens": chunk["est_tokens"], "heading_range": chunk["heading_range"],
                }],
                "est_tokens_total": chunk["est_tokens"],
                "chunk_keys": [chunk["chunk_key"]],
                "status": "planned", "output_files": [], "created_at": now,
            }
            with open(os.path.join(tsv_dir, f"wu-{wu_key}__pre__meta.json"), "w") as fp:
                json.dump(meta, fp, indent=2, ensure_ascii=False)
            wu_count += 1

    # Standalone WUs
    for s in standalone_docs:
        wu_key = s["doc_instance_key"]
        chunks = all_plans[s["doc_instance_key"]]
        meta = {
            "wu_key": wu_key, "wu_type": "standalone",
            "authority": args.authority, "doc_type": args.doc_type,
            "language": "en", "grammar_version": args.grammar_version,
            "measure_method": "tiktoken",
            "constituent_docs": [{
                "doc_instance_key": s["doc_instance_key"],
                "document_key": s["doc_key"],
                "start_line": chunks[0]["start_line"] if chunks else 1,
                "end_line": chunks[-1]["end_line"] if chunks else 1,
                "est_tokens": s["total_tokens"],
                "heading_range": chunks[0]["heading_range"] if chunks else None,
            }],
            "est_tokens_total": s["total_tokens"],
            "chunk_keys": [c["chunk_key"] for c in chunks],
            "status": "planned", "output_files": [], "created_at": now,
        }
        with open(os.path.join(tsv_dir, f"wu-{wu_key}__pre__meta.json"), "w") as fp:
            json.dump(meta, fp, indent=2, ensure_ascii=False)
        wu_count += 1

    # Merge WUs
    merge_cands.sort(key=lambda x: x["doc_instance_key"])
    current_merge, current_tokens = [], 0
    merge_groups = []

    for s in merge_cands:
        if current_tokens + s["total_tokens"] > chunk_max and current_merge:
            merge_groups.append(current_merge)
            current_merge, current_tokens = [s], s["total_tokens"]
        else:
            current_merge.append(s)
            current_tokens += s["total_tokens"]
    if current_merge:
        merge_groups.append(current_merge)

    for group in merge_groups:
        keys_str = "+".join(s["doc_instance_key"] for s in group)
        wu_key = f"merge_{hashlib.sha256(keys_str.encode()).hexdigest()[:8]}"
        constituent = []
        chunk_keys = []
        total = 0
        for s in group:
            chunks = all_plans[s["doc_instance_key"]]
            constituent.append({
                "doc_instance_key": s["doc_instance_key"],
                "document_key": s["doc_key"],
                "start_line": chunks[0]["start_line"] if chunks else 1,
                "end_line": chunks[-1]["end_line"] if chunks else 1,
                "est_tokens": s["total_tokens"],
                "heading_range": chunks[0]["heading_range"] if chunks else None,
            })
            chunk_keys.extend(c["chunk_key"] for c in chunks)
            total += s["total_tokens"]

        meta = {
            "wu_key": wu_key, "wu_type": "merged",
            "authority": args.authority, "doc_type": args.doc_type,
            "language": "en", "grammar_version": args.grammar_version,
            "measure_method": "tiktoken",
            "constituent_docs": constituent,
            "est_tokens_total": total,
            "chunk_keys": chunk_keys,
            "status": "planned", "output_files": [], "created_at": now,
        }
        with open(os.path.join(tsv_dir, f"wu-{wu_key}__pre__meta.json"), "w") as fp:
            json.dump(meta, fp, indent=2, ensure_ascii=False)
        wu_count += 1

    # Summary
    print(f"Documents: {len(doc_summaries)}")
    print(f"  Split (>{chunk_exception}): {len(split_docs)}")
    print(f"  Standalone ({wu_min}-{chunk_exception}): {len(standalone_docs)}")
    print(f"  Merge candidates (<{wu_min}): {len(merge_cands)} -> {len(merge_groups)} merge WUs")
    print(f"Total WUs: {wu_count}")


if __name__ == "__main__":
    main()
