#!/usr/bin/env python3
"""Phase B — group scan_index items by (family, series), NFD pack, claim first batch.

Usage: phase_b_plan.py <session_id> [batch_capacity]
"""

import datetime as dt
import json
import os
import sys
from pathlib import Path


WORKROOT = Path("/home/kimghw/ontology_iacs/skill_md2wu")
STALE_THRESHOLD_HOURS = 4


def cleanup_stale_locks(stale_hours: int = STALE_THRESHOLD_HOURS):
    """Remove lock files older than stale_hours.

    Judgment order: body.claimed_at/updated_at → file mtime fallback.
    Corrupt/empty lock bodies fall back to mtime.
    Returns list of removed lock filenames.
    """
    locks_dir = WORKROOT / "queue" / "locks"
    if not locks_dir.exists():
        return []
    now = dt.datetime.now(dt.timezone.utc)
    threshold = dt.timedelta(hours=stale_hours)
    removed = []
    for lock_path in locks_dir.glob("*.lock"):
        age = None
        try:
            body = json.loads(lock_path.read_text(encoding="utf-8"))
            ts_str = body.get("updated_at") or body.get("claimed_at")
            if ts_str:
                ts = dt.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=dt.timezone.utc)
                age = now - ts
        except (json.JSONDecodeError, ValueError, OSError):
            pass
        if age is None:
            try:
                mtime = dt.datetime.fromtimestamp(
                    lock_path.stat().st_mtime, dt.timezone.utc)
                age = now - mtime
            except OSError:
                continue
        if age > threshold:
            try:
                lock_path.unlink()
                removed.append(lock_path.name)
            except OSError:
                pass
    return removed


def claim_locks(item_ids, session_id):
    """Create global lock files via O_CREAT|O_EXCL for each item.

    Returns (claimed, conflicts):
      claimed  = list of item_ids successfully locked in this call.
      conflicts = list of item_ids that already existed (EEXIST).
    On EEXIST, does not overwrite; leaves existing lock untouched.
    """
    locks_dir = WORKROOT / "queue" / "locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    claimed = []
    conflicts = []
    for iid in item_ids:
        lock_path = locks_dir / f"{iid}.lock"
        body = json.dumps({
            "owner": session_id,
            "state": "pending",
            "claimed_at": now,
            "updated_at": now,
        }, ensure_ascii=False)
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            try:
                os.write(fd, body.encode("utf-8"))
            finally:
                os.close(fd)
            claimed.append(iid)
        except FileExistsError:
            conflicts.append(iid)
    return claimed, conflicts


def main():
    session_id = sys.argv[1]
    batch_capacity = int(sys.argv[2]) if len(sys.argv) > 2 else 600_000

    session_dir = WORKROOT / "queue" / "sessions" / session_id
    scan_path = session_dir / "scan" / "scan_index.json"
    plans_dir = session_dir / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)

    with open(scan_path) as f:
        scan = json.load(f)

    # Stale lock cleanup before any claim (4h threshold per SKILL.md).
    stale_removed = cleanup_stale_locks()
    if stale_removed:
        print(f"Stale locks removed ({len(stale_removed)}):")
        for name in stale_removed[:10]:
            print(f"  - {name}")

    # B-0 skip (SKILL.md §Phase B-0 + §"전역 발행 정책"):
    #   Source of truth = merge_index.json (corpora[scope].item_to_wu).
    #   Skip when every mapped wu_key has a non-empty wu-{wu_key}__pre__content.md.
    #   Per-scope manifest/item_index are session-local (audit) and MUST NOT
    #   participate in skip detection.
    skipped_items = set()
    merge_path = WORKROOT / "merge_index.json"
    if merge_path.exists():
        try:
            merge_idx = json.loads(merge_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            merge_idx = {}
        for scope, block in (merge_idx.get("corpora") or {}).items():
            for item_id, wu_keys in (block.get("item_to_wu") or {}).items():
                keys = [wu_keys] if isinstance(wu_keys, str) else list(wu_keys)
                if not keys:
                    continue
                all_ok = True
                for wk in keys:
                    cont = WORKROOT / f"wu-{wk}__pre__content.md"
                    if not (cont.exists() and cont.stat().st_size > 0):
                        all_ok = False
                        break
                if all_ok:
                    skipped_items.add(item_id)

    # Filter + group by (source_family, series)
    groups = {}
    for e in scan["files"]:
        if e["item_id"] in skipped_items:
            continue
        key = (e["source_family"], e["series"])
        groups.setdefault(key, []).append(e)

    # Sort each group by series_order asc, then item_id
    for k in groups:
        groups[k].sort(key=lambda e: (tuple(e["series_order"]), e["item_id"]))

    # Group totals & desc sort
    group_list = []
    for (fam, ser), items in groups.items():
        total = sum(i["cost_tokens"] for i in items)
        group_list.append({"family": fam, "series": ser, "items": items, "total": total})
    group_list.sort(key=lambda g: (-g["total"], g["family"], g["series"]))

    # NFD packing: keep series together if possible; oversized single item → physical-split request
    batches = []
    current = {"cost_total": 0, "items": [], "series_keys": set(), "source_family": None}

    def close_current():
        if current["items"]:
            batches.append({
                "batch_id": f"B{len(batches) + 1:03d}",
                "source_family": current["source_family"],
                "series_keys": sorted(current["series_keys"]),
                "items": current["items"],
                "cost_total": current["cost_total"],
            })

    unresolved = []

    for g in group_list:
        # Check if group fits in empty bin
        if g["total"] > batch_capacity:
            # Split group into series-order chunks that fit
            chunk_cost = 0
            chunk = []
            for it in g["items"]:
                if it["cost_tokens"] > batch_capacity:
                    unresolved.append({
                        "reason": "single_item_exceeds_capacity",
                        "item_id": it["item_id"],
                        "cost_tokens": it["cost_tokens"],
                    })
                    continue
                if chunk_cost + it["cost_tokens"] > batch_capacity:
                    # Flush chunk into a batch (own bin)
                    if chunk:
                        # If current batch empty, put chunk here; else close and open new
                        if current["cost_total"] + chunk_cost > batch_capacity:
                            close_current()
                            current = {"cost_total": 0, "items": [], "series_keys": set(), "source_family": None}
                        current["items"].extend(chunk)
                        current["cost_total"] += chunk_cost
                        current["series_keys"].add(g["series"])
                        current["source_family"] = g["family"]
                        close_current()
                        current = {"cost_total": 0, "items": [], "series_keys": set(), "source_family": None}
                    chunk = [it]
                    chunk_cost = it["cost_tokens"]
                else:
                    chunk.append(it)
                    chunk_cost += it["cost_tokens"]
            # Flush last chunk
            if chunk:
                if current["cost_total"] + chunk_cost > batch_capacity:
                    close_current()
                    current = {"cost_total": 0, "items": [], "series_keys": set(), "source_family": None}
                current["items"].extend(chunk)
                current["cost_total"] += chunk_cost
                current["series_keys"].add(g["series"])
                current["source_family"] = g["family"]
            continue

        # Entire group as one atomic unit (series continuity)
        if current["cost_total"] + g["total"] > batch_capacity:
            close_current()
            current = {"cost_total": 0, "items": [], "series_keys": set(), "source_family": None}
        current["items"].extend(g["items"])
        current["cost_total"] += g["total"]
        current["series_keys"].add(g["series"])
        current["source_family"] = g["family"]

    close_current()

    # Normalize batch item payloads
    for b in batches:
        b["items"] = [{"item_id": x["item_id"], "cost_tokens": x["cost_tokens"],
                       "series_order": x["series_order"], "filepath": x["filepath"],
                       "series": x["series"], "document_key": x["document_key"]}
                      for x in b["items"]]

    # Claim: iterate batches in order. Claim the first batch that yields at
    # least one successful lock. Earlier batches with 100% conflict are marked
    # "aborted_by_conflict" so Phase C can skip them and the next batch wins.
    # Remaining batches stay "reserved_for_other_session".
    lock_conflicts = []
    claimed_idx = -1
    for i, b in enumerate(batches):
        if claimed_idx != -1:
            b["status"] = "reserved_for_other_session"
            continue
        ids = [it["item_id"] for it in b["items"]]
        claimed, conflicts = claim_locks(ids, session_id)
        b["locked_items"] = claimed
        b["lock_conflicts"] = conflicts
        lock_conflicts.extend(conflicts)
        if claimed:
            b["status"] = "claimed"
            claimed_idx = i
        else:
            b["status"] = "aborted_by_conflict"

    plan = {
        "session_id": session_id,
        "source_dir": scan["source_dir"],
        "batch_capacity": batch_capacity,
        "session_capacity": batch_capacity,
        "total_input_items": scan["total_files"],
        "skipped_items": len(skipped_items),
        "batches": batches,
        "unresolved": unresolved,
    }

    plan_path = plans_dir / "batch_plan.json"
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)

    print(f"=== Phase B done ===")
    print(f"batch_capacity: {batch_capacity:,}")
    print(f"batches: {len(batches)}")
    for b in batches:
        print(f"  {b['batch_id']} [{b['status']}] family={b['source_family']} "
              f"series={','.join(b['series_keys'])} items={len(b['items'])} "
              f"tokens={b['cost_total']:,}")
        if b["status"] == "claimed":
            print(f"    locks claimed: {len(b.get('locked_items', []))}/{len(b['items'])}")
            if b.get("lock_conflicts"):
                print(f"    lock conflicts (EEXIST, skipped): {len(b['lock_conflicts'])}")
                for iid in b["lock_conflicts"][:5]:
                    print(f"      - {iid}")
        elif b["status"] == "aborted_by_conflict":
            print(f"    aborted: 100% lock conflict ({len(b['items'])} items)")
            for iid in b.get("lock_conflicts", [])[:5]:
                print(f"      - {iid}")
    if unresolved:
        print(f"unresolved: {len(unresolved)}")
        for u in unresolved:
            print(f"  {u}")
    print(f"Written: {plan_path}")


if __name__ == "__main__":
    main()
