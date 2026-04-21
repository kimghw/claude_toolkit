#!/usr/bin/env python3
"""Phase C for IACS UI — claim locks, chunk/WU packing, emit WU content + manifest.

Usage: phase_c_execute_ui.py <session_id>

Reads:
  queue/sessions/<session_id>/plans/batch_plan.json
  queue/sessions/<session_id>/parts/doc_parts.json  (items[<item_id>].headings)
Writes:
  queue/locks/<item_id>.lock                        (global, EEXIST atomic)
  queue/sessions/<session_id>/working/<item_id>/    (per-item working dir)
  queue/sessions/<session_id>/out/wu-<wu_key>__pre__{meta.json,content.md}
  queue/sessions/<session_id>/parts/doc_parts.json  (chunk_plan filled in-place)
  Publishes (SKILL.md §"전역 발행 정책"):
  skill_md2wu/wu-<wu_key>__pre__content.md
  skill_md2wu/merge_index.json    (atomic rename, written LAST)

  Session-local (T2/T5 — audit only, NOT promoted):
  queue/sessions/<session_id>/out/corpus-<scope>__pre__manifest.json
  queue/sessions/<session_id>/out/corpus-<scope>__md2wu__issue_gate_report.json
"""

import hashlib
import json
import os
import shutil
import sys
import errno
from datetime import datetime, timezone
from pathlib import Path


WORKROOT = Path(os.environ.get("MD2WU_WORKROOT") or Path.cwd()).resolve()
CHUNK_MAX = 32_000
CHUNK_EXCEPTION = 48_000  # 1.5x
WU_MIN = 16_000
AUTHORITY = "IACS"
DOC_TYPE = "UI"
LANGUAGE = "en"
GRAMMAR_VERSION = "iacs_ui_v01"
SOURCE_FAMILY = "iacs_ui"


sys.path.insert(0, str(Path(__file__).resolve().parent))
import chunk_wu as cw  # reuse chunk planner


def acquire_lock(lock_path: Path, session_id: str, item_id: str):
    """Atomic O_CREAT|O_EXCL lock. If held by the same session, reuse it;
    raise EEXIST only when another session owns it."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "session_id": session_id,
        "item_id": item_id,
        "phase": "pending",
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            os.write(fd, json.dumps(body, ensure_ascii=False).encode("utf-8"))
        finally:
            os.close(fd)
        return
    except FileExistsError:
        try:
            existing = json.loads(lock_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raise OSError(errno.EEXIST, "lock exists with unparseable body")
        owner = existing.get("owner") or existing.get("session_id")
        if owner == session_id:
            return
        raise OSError(errno.EEXIST, f"lock held by another session: {owner}")


def update_lock(lock_path: Path, phase: str, session_id: str, item_id: str):
    body = {
        "session_id": session_id,
        "item_id": item_id,
        "phase": phase,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp = lock_path.with_suffix(".lock.tmp")
    tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(lock_path))


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def main():
    session_id = sys.argv[1]
    session_dir = WORKROOT / "queue" / "sessions" / session_id
    plan_path = session_dir / "plans" / "batch_plan.json"
    parts_dir = session_dir / "parts"
    out_dir = session_dir / "out"
    working_root = session_dir / "working"
    out_dir.mkdir(parents=True, exist_ok=True)
    working_root.mkdir(parents=True, exist_ok=True)

    with open(plan_path) as f:
        plan = json.load(f)

    claimed = next((b for b in plan["batches"] if b["status"] == "claimed"), None)
    if not claimed:
        print("No claimed batch found.")
        sys.exit(1)

    items = claimed["items"]
    print(f"Claimed batch {claimed['batch_id']}: {len(items)} items, {claimed['cost_total']:,} tokens")
    print(f"Series: {claimed['series_keys']}")

    locks_dir = WORKROOT / "queue" / "locks"
    acquired_locks = []
    lock_failures = []
    for it in items:
        lock_path = locks_dir / f"{it['item_id']}.lock"
        try:
            acquire_lock(lock_path, session_id, it["item_id"])
            acquired_locks.append((it, lock_path))
        except OSError as e:
            if e.errno == errno.EEXIST:
                lock_failures.append((it["item_id"], "already_locked"))
                print(f"  LOCK SKIP (held): {it['item_id']}")
            else:
                lock_failures.append((it["item_id"], str(e)))
                print(f"  LOCK FAIL: {it['item_id']} - {e}")

    print(f"Locks acquired: {len(acquired_locks)}/{len(items)}")

    if not acquired_locks:
        print("No locks acquired. Abort.")
        sys.exit(2)

    for it, lp in acquired_locks:
        update_lock(lp, "working", session_id, it["item_id"])
        (working_root / it["item_id"]).mkdir(parents=True, exist_ok=True)

    doc_parts_path = parts_dir / "doc_parts.json"
    with open(doc_parts_path, encoding="utf-8") as f:
        doc_parts = json.load(f)
    doc_parts_items = doc_parts["items"]

    now = now_iso()
    all_plans = {}
    doc_summaries = []
    item_meta_by_id = {it["item_id"]: it for it, _ in acquired_locks}
    judgments = []
    threshold_issues = []

    for it, _ in acquired_locks:
        item_id = it["item_id"]
        entry = doc_parts_items.get(item_id)
        if entry is None or not entry.get("headings"):
            print(f"  HEADINGS MISSING: {item_id}")
            continue
        headings = entry["headings"]
        total_tokens = headings[0]["est_tokens_inclusive"] if headings else 0
        chunks = cw.create_chunk_plan(item_id, headings, total_tokens,
                                      CHUNK_MAX, CHUNK_EXCEPTION, WU_MIN)
        all_plans[item_id] = chunks
        entry["chunk_plan"] = chunks
        dk = it["document_key"]
        doc_summaries.append({
            "doc_instance_key": item_id,
            "doc_key": dk,
            "total_tokens": total_tokens,
            "chunk_count": len(chunks),
            "filepath": it["filepath"],
            "series": it["series"],
            "series_order": it["series_order"],
        })

    with open(doc_parts_path, "w", encoding="utf-8") as f:
        json.dump(doc_parts, f, ensure_ascii=False, indent=2)

    split_docs = [s for s in doc_summaries if s["total_tokens"] > CHUNK_EXCEPTION]
    standalone_docs = [s for s in doc_summaries if WU_MIN <= s["total_tokens"] <= CHUNK_EXCEPTION]
    merge_cands = [s for s in doc_summaries if s["total_tokens"] < WU_MIN]

    print(f"Docs: split={len(split_docs)}, standalone={len(standalone_docs)}, merge_cands={len(merge_cands)}")

    wus = []  # list of (meta_dict, content_text, series_key)

    def read_lines(fp):
        with open(fp, encoding="utf-8", errors="replace") as f:
            return f.readlines()

    # Split WUs
    for s in split_docs:
        lines = read_lines(s["filepath"])
        for i, chunk in enumerate(all_plans[s["doc_instance_key"]]):
            wu_key = f"{s['doc_instance_key']}_wu{i + 1:03d}"
            content = "".join(lines[chunk["start_line"] - 1: chunk["end_line"]])
            if chunk["est_tokens"] > CHUNK_EXCEPTION:
                threshold_issues.append({
                    "type": "oversize_hard",
                    "severity": "HIGH",
                    "wu_key": wu_key,
                    "tokens": chunk["est_tokens"],
                })
            elif chunk["est_tokens"] > CHUNK_MAX:
                threshold_issues.append({
                    "type": "oversize_exception",
                    "severity": "INFO",
                    "wu_key": wu_key,
                    "tokens": chunk["est_tokens"],
                })
            meta = {
                "wu_key": wu_key,
                "wu_type": "split",
                "authority": AUTHORITY,
                "doc_type": DOC_TYPE,
                "language": LANGUAGE,
                "grammar_version": GRAMMAR_VERSION,
                "measure_method": "tiktoken",
                "constituent_docs": [{
                    "doc_instance_key": s["doc_instance_key"],
                    "document_key": s["doc_key"],
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"],
                    "est_tokens": chunk["est_tokens"],
                    "heading_range": chunk["heading_range"],
                }],
                "est_tokens_total": chunk["est_tokens"],
                "chunk_keys": [chunk["chunk_key"]],
                "status": "processed",
                "output_files": [],
                "created_at": now,
            }
            wus.append((meta, content, s["series"]))

    # Standalone WUs
    for s in standalone_docs:
        lines = read_lines(s["filepath"])
        chunks = all_plans[s["doc_instance_key"]]
        wu_key = s["doc_instance_key"]
        start = chunks[0]["start_line"] if chunks else 1
        end = chunks[-1]["end_line"] if chunks else len(lines)
        content = "".join(lines[start - 1: end])
        meta = {
            "wu_key": wu_key,
            "wu_type": "standalone",
            "authority": AUTHORITY,
            "doc_type": DOC_TYPE,
            "language": LANGUAGE,
            "grammar_version": GRAMMAR_VERSION,
            "measure_method": "tiktoken",
            "constituent_docs": [{
                "doc_instance_key": s["doc_instance_key"],
                "document_key": s["doc_key"],
                "start_line": start,
                "end_line": end,
                "est_tokens": s["total_tokens"],
                "heading_range": chunks[0]["heading_range"] if chunks else None,
            }],
            "est_tokens_total": s["total_tokens"],
            "chunk_keys": [c["chunk_key"] for c in chunks],
            "status": "processed",
            "output_files": [],
            "created_at": now,
        }
        wus.append((meta, content, s["series"]))

    # Merge WUs — group per series (active/_del kept separate via series key),
    # sort by series_order.
    merge_cands.sort(key=lambda x: (x["series"], tuple(x["series_order"]), x["doc_instance_key"]))
    merge_groups = []
    current = []
    current_tokens = 0
    current_series = None
    for s in merge_cands:
        if current_series is not None and s["series"] != current_series:
            if current:
                merge_groups.append((current, current_series))
            current, current_tokens = [], 0
        if current_tokens + s["total_tokens"] > CHUNK_MAX and current:
            merge_groups.append((current, current_series))
            current, current_tokens = [], 0
        current.append(s)
        current_tokens += s["total_tokens"]
        current_series = s["series"]
    if current:
        merge_groups.append((current, current_series))

    for group, group_series in merge_groups:
        keys_str = "+".join(s["doc_instance_key"] for s in group)
        wu_key = f"iacs_ui_merge_{hashlib.sha256(keys_str.encode()).hexdigest()[:8]}"
        constituent = []
        chunk_keys = []
        total = 0
        content_parts = []
        for s in group:
            chunks = all_plans[s["doc_instance_key"]]
            lines = read_lines(s["filepath"])
            start = chunks[0]["start_line"] if chunks else 1
            end = chunks[-1]["end_line"] if chunks else len(lines)
            content_parts.append("".join(lines[start - 1: end]).rstrip() + "\n\n")
            constituent.append({
                "doc_instance_key": s["doc_instance_key"],
                "document_key": s["doc_key"],
                "start_line": start,
                "end_line": end,
                "est_tokens": s["total_tokens"],
                "heading_range": chunks[0]["heading_range"] if chunks else None,
            })
            chunk_keys.extend(c["chunk_key"] for c in chunks)
            total += s["total_tokens"]

        if total < WU_MIN:
            threshold_issues.append({
                "type": "undersized",
                "severity": "LOW",
                "wu_key": wu_key,
                "tokens": total,
            })

        meta = {
            "wu_key": wu_key,
            "wu_type": "merged",
            "authority": AUTHORITY,
            "doc_type": DOC_TYPE,
            "language": LANGUAGE,
            "grammar_version": GRAMMAR_VERSION,
            "measure_method": "tiktoken",
            "constituent_docs": constituent,
            "est_tokens_total": total,
            "chunk_keys": chunk_keys,
            "status": "processed",
            "output_files": [],
            "created_at": now,
        }
        wus.append((meta, "".join(content_parts), group_series))

    scan_path = session_dir / "scan" / "scan_index.json"
    with open(scan_path) as f:
        scan = json.load(f)
    for err in scan.get("additivity_errors", []):
        if err["item"] not in item_meta_by_id:
            continue
        judgments.append({
            "stage": "S2",
            "severity": "LOW",
            "category": "tokenizer_rounding",
            "target": err["item"],
            "ambiguity": "parent.exclusive + sum(children.inclusive) differs by ±1 token",
            "decision": "Accept as BPE boundary rounding; does not affect packing decisions",
            "risk": "Negligible — token counts may differ by 1 at heading boundaries",
        })

    for meta, content, _series in wus:
        meta_path = out_dir / f"wu-{meta['wu_key']}__pre__meta.json"
        content_path = out_dir / f"wu-{meta['wu_key']}__pre__content.md"
        meta["output_files"] = [
            f"skill_md2wu/wu-{meta['wu_key']}__pre__content.md",
        ]
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        content_path.write_text(content, encoding="utf-8")

    for it, lp in acquired_locks:
        update_lock(lp, "publishing", session_id, it["item_id"])

    # Group WUs by series (series already carried on each WU tuple)
    wus_by_series = {}
    for meta, content, series_key in wus:
        wus_by_series.setdefault(series_key, []).append((meta, content))

    # Publish content.md globally
    for meta, content, _ in wus:
        src_cont = out_dir / f"wu-{meta['wu_key']}__pre__content.md"
        dst_cont = WORKROOT / f"wu-{meta['wu_key']}__pre__content.md"
        shutil.copy2(str(src_cont), str(dst_cont))

    # Session-local manifest + issue gate per scope; global merge_index last.
    scope_to_item_to_wu: dict[str, dict[str, list[str]]] = {}
    for series_key, group_wus in wus_by_series.items():
        # scope = iacs_ui_{series_short}[_del]; strip leading "ui_"
        scope = f"iacs_ui_{series_key[len('ui_'):]}"
        manifest = {
            "corpus_scope": scope,
            "source_family": SOURCE_FAMILY,
            "authority": AUTHORITY,
            "doc_type": DOC_TYPE,
            "language": LANGUAGE,
            "grammar_version": GRAMMAR_VERSION,
            "measure_method": "tiktoken",
            "series": series_key,
            "session_id": session_id,
            "batch_id": claimed["batch_id"],
            "generated_at": now,
            "wu_count": len(group_wus),
            "est_tokens_total": sum(m["est_tokens_total"] for m, _ in group_wus),
            "work_units": [
                {
                    "wu_key": m["wu_key"],
                    "wu_type": m["wu_type"],
                    "constituent_docs": m["constituent_docs"],
                    "est_tokens_total": m["est_tokens_total"],
                    "chunk_keys": m["chunk_keys"],
                    "status": m["status"],
                    "content_file": f"wu-{m['wu_key']}__pre__content.md",
                }
                for m, _ in group_wus
            ],
        }
        manifest_path = out_dir / f"corpus-{scope}__pre__manifest.json"
        manifest_tmp = manifest_path.with_suffix(".json.tmp")
        manifest_tmp.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(str(manifest_tmp), str(manifest_path))

        scope_issues = [i for i in threshold_issues
                        if any(i["wu_key"] == m["wu_key"] for m, _ in group_wus)]
        scope_judgments = [j for j in judgments
                           if any(j["target"] == c["doc_instance_key"]
                                  for m, _ in group_wus for c in m["constituent_docs"])]
        igr = {
            "corpus_scope": scope,
            "generated_at": now,
            "threshold_issues": scope_issues,
            "judgments": scope_judgments,
        }
        igr_path = out_dir / f"corpus-{scope}__md2wu__issue_gate_report.json"
        igr_tmp = igr_path.with_suffix(".json.tmp")
        igr_tmp.write_text(
            json.dumps(igr, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(str(igr_tmp), str(igr_path))

        item_to_wu: dict[str, list[str]] = {}
        for m, _ in group_wus:
            for c in m["constituent_docs"]:
                item_to_wu.setdefault(c["doc_instance_key"], []).append(m["wu_key"])
        scope_to_item_to_wu[scope] = item_to_wu

    # Global merge_index.json (last commit)
    merge_path = WORKROOT / "merge_index.json"
    if merge_path.exists():
        try:
            existing = json.loads(merge_path.read_text(encoding="utf-8"))
            corpora = existing.get("corpora", {}) or {}
        except (json.JSONDecodeError, OSError):
            corpora = {}
    else:
        corpora = {}
    for scope, item_to_wu in scope_to_item_to_wu.items():
        corpora[scope] = {"item_to_wu": item_to_wu}
    merge_payload = {
        "generated_at": now,
        "corpora": corpora,
    }
    merge_tmp = merge_path.with_suffix(".json.tmp")
    merge_tmp.write_text(
        json.dumps(merge_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(str(merge_tmp), str(merge_path))

    for it, lp in acquired_locks:
        try:
            os.unlink(str(lp))
        except FileNotFoundError:
            pass

    print()
    print("=== Phase C (UI) done ===")
    print(f"WUs published: {len(wus)}")
    for series_key, group_wus in wus_by_series.items():
        print(f"  {series_key}: {len(group_wus)} WUs "
              f"({sum(m['est_tokens_total'] for m, _ in group_wus):,} tokens)")
    print(f"Threshold issues: {len(threshold_issues)}")
    print(f"Judgments: {len(judgments)}")
    print(f"Lock failures: {len(lock_failures)}")
    print(f"Scopes published: {sorted(scope_to_item_to_wu.keys())}")


if __name__ == "__main__":
    main()
