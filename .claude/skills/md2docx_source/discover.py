#!/usr/bin/env python3
"""
md2docx_source/discover.py — strip_patterns.json 카탈로그 발견·검증·등록 보조 도구

LLM 에이전트가 새 source(.md) 를 만났을 때 헤딩·번호 인벤토리를 보고
strip_patterns.json 에 추가할 패턴을 제안·검증·등록하는 흐름을 돕는다.

설계 원칙:
    - 스크립트는 **관찰·추출·검증** 만 한다 (LLM 의 판단을 대체하지 않음).
    - 패턴 **선정·작성** 은 LLM 이 inventory/diff 결과를 보고 결정한다.
    - 카탈로그 변경은 validate 통과한 entry 만 add 로 반영된다.

흐름:
    1) inventory <source.md>   — source 의 heading/번호 구조 출력 (LLM 관찰용)
    2) diff      <source.md>   — 현재 카탈로그가 잡지 못한 후보 (LLM 제안 입력)
    3) validate  <entry.json>  — 제안된 패턴 entry 의 regex/sample 일관성 검증
    4) add       <entry.json>  — validate 통과 후 strip_patterns.json 에 append
    5) self-test               — 카탈로그 모든 entry 의 sample re-apply 검증

원본 source 와 strip 엔진(strip.py) 은 변경하지 않는다.
"""

import argparse
import json
import re
import sys
import threading
from pathlib import Path


HERE = Path(__file__).resolve().parent
CATALOG_PATH = HERE / "references" / "strip_patterns.json"

HEADING_RE = re.compile(r"^(#+)\s+(.+?)\s*$", re.MULTILINE)
HEADING_NUMBER_PREFIX_RE = re.compile(r"^\d+(?:[.-]\d+)*\.?(?=\s|$)")
BOLD_NUMBER_PREFIX_RE = re.compile(r"\*\*(\d+(?:[.-]\d+)+)\.?\s+", re.MULTILINE)
ORDERED_LIST_RE = re.compile(r"^(\s*)(\d+)[.)]\s+", re.MULTILINE)
BULLET_LIST_RE = re.compile(r"^(\s*)([-*+])\s+", re.MULTILINE)
HRULE_RE = re.compile(r"^[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*$", re.MULTILINE)


def _parse_flags(flag_str):
    flags = 0
    for f in (flag_str or "").split("|"):
        f = f.strip().upper()
        if f == "MULTILINE":
            flags |= re.MULTILINE
        elif f == "IGNORECASE":
            flags |= re.IGNORECASE
        elif f == "DOTALL":
            flags |= re.DOTALL
    return flags


def load_catalog():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _classify_separator(num: str) -> str:
    body = num.rstrip(".")
    has_dot = "." in body
    has_dash = "-" in body
    if has_dot and has_dash:
        return "mixed"
    if has_dash:
        return "dash"
    if has_dot:
        return "dot"
    return "single"


def inventory(source_path: Path) -> dict:
    """source 의 heading·번호 구조 인벤토리."""
    text = source_path.read_text(encoding="utf-8")

    headings = []
    for m in HEADING_RE.finditer(text):
        level = len(m.group(1))
        title = m.group(2)
        num_m = HEADING_NUMBER_PREFIX_RE.match(title)
        headings.append({
            "level": level,
            "line": f"{'#' * level} {title}",
            "title": title,
            "manual_number": num_m.group(0) if num_m else None,
        })

    headings_with_num = [h for h in headings if h["manual_number"]]
    separators = {}
    for h in headings_with_num:
        sep = _classify_separator(h["manual_number"])
        separators.setdefault(sep, []).append(h["manual_number"])

    bold_numbers = []
    for m in BOLD_NUMBER_PREFIX_RE.finditer(text):
        bold_numbers.append({
            "prefix": m.group(1),
            "separator": _classify_separator(m.group(1)),
            "sample": m.group(0).strip(),
        })

    ordered_items = ORDERED_LIST_RE.findall(text)
    bullet_items = BULLET_LIST_RE.findall(text)
    hrules = HRULE_RE.findall(text)

    return {
        "source": str(source_path),
        "heading": {
            "total": len(headings),
            "with_manual_number": len(headings_with_num),
            "separators": {k: sorted(set(v))[:8] for k, v in separators.items()},
            "examples": [h["line"] for h in headings_with_num[:10]],
        },
        "bold_manual_number": {
            "total": len(bold_numbers),
            "separators": sorted({b["separator"] for b in bold_numbers}),
            "examples": [b["sample"] for b in bold_numbers[:10]],
        },
        "list": {
            "ordered_items": len(ordered_items),
            "bullet_items": len(bullet_items),
        },
        "hrule": {"total": len(hrules)},
    }


def _compile_remove_patterns(catalog):
    """카탈로그의 모든 remove 패턴 (passes 포함) 을 (id, regex) 목록으로 컴파일."""
    out = []
    for entry in catalog.get("patterns", []):
        if entry.get("kind") != "remove":
            continue
        try:
            if "passes" in entry:
                for sub in entry["passes"]:
                    out.append((entry["id"], re.compile(sub["pattern"], _parse_flags(sub.get("flags")))))
            else:
                out.append((entry["id"], re.compile(entry["pattern"], _parse_flags(entry.get("flags")))))
        except re.error:
            continue
    return out


def diff_unmatched(source_path: Path) -> dict:
    """현재 카탈로그가 잡지 못한 inventory 후보."""
    text = source_path.read_text(encoding="utf-8")
    catalog = load_catalog()
    compiled = _compile_remove_patterns(catalog)

    unmatched_headings = []
    for m in HEADING_RE.finditer(text):
        line = f"{'#' * len(m.group(1))} {m.group(2)}"
        if not HEADING_NUMBER_PREFIX_RE.match(m.group(2)):
            continue
        if not any(p.search(line) for _id, p in compiled):
            unmatched_headings.append(line)

    unmatched_bolds = []
    bold_probe = re.compile(r"\*\*\d+(?:[.-]\d+)*[^\*]*?\*\*", re.MULTILINE)
    for m in bold_probe.finditer(text):
        snippet = m.group(0)
        if not re.match(r"\*\*\d+(?:[.-]\d+)+", snippet):
            continue
        if not any(p.search(snippet) for _id, p in compiled):
            if snippet not in unmatched_bolds:
                unmatched_bolds.append(snippet)

    return {
        "source": str(source_path),
        "catalog_size": len({i for i, _ in compiled}),
        "unmatched_heading_with_number": unmatched_headings[:30],
        "unmatched_bold_with_number": unmatched_bolds[:30],
        "_note": (
            "이 후보들이 모두 패턴이 돼야 한다는 뜻은 아닙니다. "
            "LLM 이 inventory 와 함께 보고 추가 가치 있는 것만 entry 로 작성하세요."
        ),
    }


def _regex_timeout_check(pattern, timeout=1.0):
    """별도 스레드로 findall — catastrophic backtracking 간이 검사."""
    probe = ("ab12-34.56 " * 200) + ("**1-2-3 ** " * 50)
    result = [None]

    def run():
        try:
            pattern.findall(probe)
            result[0] = "ok"
        except Exception as e:
            result[0] = f"runtime error: {e}"

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        return f"regex took >{timeout}s on probe input — possible catastrophic backtracking"
    return None


def _apply_entry(entry: dict, text: str) -> str:
    """entry 의 pattern(s) 를 text 에 순차 적용해 결과 반환 (sample 검증용)."""
    if "passes" in entry:
        out = text
        for sub in entry["passes"]:
            regex = re.compile(sub["pattern"], _parse_flags(sub.get("flags")))
            out = regex.sub(sub["replace"], out)
        return out
    regex = re.compile(entry["pattern"], _parse_flags(entry.get("flags")))
    return regex.sub(entry["replace"], text)


def validate_entry(entry: dict, allow_existing_id: bool = False) -> list:
    """제안된 entry 의 구조·regex·sample 일관성 검증. 오류 메시지 리스트 반환."""
    errors = []

    base_required = ["id", "kind", "sample"]
    for f in base_required:
        if f not in entry:
            errors.append(f"missing field: {f}")
    if errors:
        return errors

    if not re.match(r"^[a-z][a-z0-9-]*$", entry["id"]):
        errors.append(f"id must be kebab-case (a-z, 0-9, '-'): {entry['id']!r}")
    if entry["kind"] not in ("remove", "promote"):
        errors.append(f"kind must be 'remove' or 'promote': {entry['kind']!r}")

    if not allow_existing_id:
        catalog = load_catalog()
        existing = {p["id"] for p in catalog.get("patterns", [])}
        if entry["id"] in existing:
            errors.append(f"id already exists in catalog: {entry['id']!r}")

    sample = entry.get("sample")
    if not isinstance(sample, dict) or "before" not in sample or "after" not in sample:
        errors.append("sample must be an object with 'before' and 'after' fields")

    has_passes = "passes" in entry
    has_single = "pattern" in entry and "replace" in entry
    if not (has_passes or has_single):
        errors.append("either {pattern, replace} or {passes: [{pattern, replace, ...}, ...]} required")

    if errors:
        return errors

    if has_passes:
        for i, sub in enumerate(entry["passes"]):
            for fld in ("pattern", "replace"):
                if fld not in sub:
                    errors.append(f"passes[{i}].{fld} missing")
                    return errors
            try:
                re.compile(sub["pattern"], _parse_flags(sub.get("flags")))
            except re.error as e:
                errors.append(f"passes[{i}].pattern regex error: {e}")
                return errors
    else:
        try:
            regex = re.compile(entry["pattern"], _parse_flags(entry.get("flags")))
        except re.error as e:
            errors.append(f"pattern regex error: {e}")
            return errors

        if not regex.search(sample["before"]):
            errors.append(f"pattern does not match sample.before: {sample['before']!r}")
            return errors

        bt_err = _regex_timeout_check(regex)
        if bt_err:
            errors.append(bt_err)

    try:
        actual = _apply_entry(entry, sample["before"])
    except Exception as e:
        errors.append(f"applying entry on sample.before raised: {e}")
        return errors

    if actual != sample["after"]:
        errors.append(
            "applied pattern result mismatches sample.after\n"
            f"  expected: {sample['after']!r}\n"
            f"  actual:   {actual!r}"
        )

    return errors


def add_entry(entry: dict) -> None:
    """validate 통과 후 catalog 끝에 append."""
    errors = validate_entry(entry)
    if errors:
        print("[ADD-FAIL]")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    catalog = load_catalog()
    catalog["patterns"].append(entry)
    CATALOG_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[ADD-OK] {entry['id']} (kind={entry['kind']}) → {CATALOG_PATH.name}")
    print(f"  카탈로그 크기: {len(catalog['patterns'])} 패턴")


def self_test() -> int:
    """카탈로그의 모든 entry 에 대해 sample re-apply 가 일관되는지 확인."""
    catalog = load_catalog()
    n_ok = n_fail = 0
    print(f"[SELF-TEST] {CATALOG_PATH.name}: {len(catalog.get('patterns', []))} 패턴")
    for entry in catalog.get("patterns", []):
        errors = validate_entry(entry, allow_existing_id=True)
        if errors:
            n_fail += 1
            print(f"  [FAIL] {entry.get('id', '?')}")
            for e in errors:
                print(f"      {e}")
        else:
            n_ok += 1
            print(f"  [OK]   {entry['id']}")
    print(f"[SELF-TEST-RESULT] OK={n_ok}, FAIL={n_fail}")
    return 0 if n_fail == 0 else 1


def load_entry_arg(arg: str) -> dict:
    if arg == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(arg).read_text(encoding="utf-8"))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        prog="discover.py",
        description="strip_patterns.json 패턴 발견·검증·등록 보조 (LLM-driven)",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_inv = sub.add_parser("inventory", help="source 의 heading·번호 인벤토리 (LLM 관찰용)")
    p_inv.add_argument("source", type=Path)

    p_diff = sub.add_parser("diff", help="현재 카탈로그가 잡지 못한 후보 (LLM 제안 입력)")
    p_diff.add_argument("source", type=Path)

    p_val = sub.add_parser("validate", help="제안된 entry JSON 검증 (regex/sample 일관성)")
    p_val.add_argument("entry", help="entry JSON 파일 경로 또는 '-' (stdin)")

    p_add = sub.add_parser("add", help="validate 통과 후 catalog 에 append")
    p_add.add_argument("entry", help="entry JSON 파일 경로 또는 '-' (stdin)")

    sub.add_parser("self-test", help="카탈로그의 모든 sample 재검증")

    args = ap.parse_args()

    if args.cmd == "inventory":
        if not args.source.exists():
            sys.exit(f"ERROR: 파일 없음: {args.source}")
        print(json.dumps(inventory(args.source), ensure_ascii=False, indent=2))
    elif args.cmd == "diff":
        if not args.source.exists():
            sys.exit(f"ERROR: 파일 없음: {args.source}")
        result = diff_unmatched(args.source)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        cand = result["unmatched_heading_with_number"] + result["unmatched_bold_with_number"]
        if cand:
            print(f"\n[DISCOVER-CANDIDATES] {len(cand)} 줄이 카탈로그에 매칭되지 않음 — 패턴 추가 검토 권장")
            sys.exit(3)
        print("\n[DISCOVER-CLEAN] 모든 heading·bold 매뉴얼 번호가 카탈로그로 커버됨")
    elif args.cmd == "validate":
        entry = load_entry_arg(args.entry)
        errors = validate_entry(entry)
        if errors:
            print("[VALIDATE-FAIL]")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        print(f"[VALIDATE-OK] {entry.get('id', '?')} (kind={entry.get('kind')})")
    elif args.cmd == "add":
        entry = load_entry_arg(args.entry)
        add_entry(entry)
    elif args.cmd == "self-test":
        sys.exit(self_test())


if __name__ == "__main__":
    main()
