#!/usr/bin/env python3
"""
md2docx/strip.py — 회사 양식과 충돌하는 markdown 패턴 검출·치환

references/strip_patterns.json 에 정의된 정규식 패턴을 markdown 파일에서 검출.
사용자 확인을 받아 선택된 패턴만 적용(치환)한다.

**원본 .md 는 절대 수정하지 않는다.** 치환 결과는 같은 폴더에 접미사
`_stripped` 를 붙인 새 파일(`<원본>_stripped.md`)로 저장.

작동 흐름 (md2docx.py 의 Step 1.7 에서 호출):
    1) 검출 모드(기본): 각 패턴 매칭 수와 샘플을 [STRIP-MATCH] 로 출력. 매칭 있으면 exit 3.
    2) Claude 가 AskUserQuestion 으로 패턴별 제거 여부 확인.
    3) "제거" 답들을 모아 md2docx.py 를 `--apply-strip <pid,pid,...>` 로 재실행,
       또는 strip.py --apply <pid> 로 직접 `<원본>_stripped.md` 생성.

Usage:
    python strip.py <md>                          # 검출만 (exit 0 = 매칭 없음, 3 = 있음)
    python strip.py <md> --json                   # 결과 JSON
    python strip.py <md> --apply <pid> [<pid>...] # 선택된 패턴 적용 → <md_stem>_stripped.md
    python strip.py <md> --apply <pid> --out X.md # 출력 경로 명시
    python strip.py --list                        # 정의된 패턴 목록만 보기

종료 코드:
    0 = 매칭 없음 또는 apply 성공
    1 = 실행 오류
    3 = 사용자 확인이 필요한 매칭 발견
"""

import argparse
import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
PATTERNS_PATH = REPO_ROOT / "references" / "strip_patterns.json"
STRIPPED_SUFFIX = "_stripped"


def stripped_path_for(md_path: Path) -> Path:
    """`<stem>_stripped.md` 경로. 이미 `_stripped` 로 끝나면 그대로 반환."""
    if md_path.stem.endswith(STRIPPED_SUFFIX):
        return md_path
    return md_path.with_name(md_path.stem + STRIPPED_SUFFIX + md_path.suffix)


def load_patterns():
    if not PATTERNS_PATH.exists():
        return []
    data = json.loads(PATTERNS_PATH.read_text(encoding="utf-8"))
    return data.get("patterns", [])


def compile_pattern(p):
    flags = 0
    for f in (p.get("flags") or "").split("|"):
        f = f.strip().upper()
        if f == "MULTILINE":
            flags |= re.MULTILINE
        elif f == "IGNORECASE":
            flags |= re.IGNORECASE
        elif f == "DOTALL":
            flags |= re.DOTALL
    return re.compile(p["pattern"], flags)


def find_matches(text, patterns):
    """패턴별 매칭 결과 반환."""
    results = []
    lines = text.split("\n")
    for p in patterns:
        regex = compile_pattern(p)
        matches = list(regex.finditer(text))
        if not matches:
            continue
        samples = []
        seen_lines = set()
        for m in matches:
            line_no = text.count("\n", 0, m.start()) + 1
            if line_no in seen_lines:
                continue
            seen_lines.add(line_no)
            line = lines[line_no - 1]
            after = regex.sub(p["replace"], line)
            samples.append({"line": line_no, "before": line, "after": after})
            if len(samples) >= 5:
                break
        results.append({
            "id": p["id"],
            "kind": p.get("kind", "remove"),
            "name": p["name"],
            "description": p.get("description", ""),
            "reason": p.get("reason", ""),
            "count": len(matches),
            "samples": samples,
        })
    return results


def apply_patterns(md_path, pattern_ids, patterns, out_path):
    """원본 md_path 는 읽기 전용. 치환 결과는 out_path 로 저장."""
    text = md_path.read_text(encoding="utf-8")
    by_id = {p["id"]: p for p in patterns}
    applied = []
    unknown = []
    for pid in pattern_ids:
        p = by_id.get(pid)
        if not p:
            unknown.append(pid)
            continue
        regex = compile_pattern(p)
        new_text, n = regex.subn(p["replace"], text)
        if n > 0:
            text = new_text
            applied.append({"id": pid, "count": n})
        else:
            applied.append({"id": pid, "count": 0})

    out_path.write_text(text, encoding="utf-8")
    return applied, unknown


def main():
    ap = argparse.ArgumentParser(description="회사 양식 충돌 패턴 검출·치환")
    ap.add_argument("md", nargs="?", help="대상 markdown 파일 (원본은 수정되지 않음)")
    ap.add_argument("--apply", nargs="+", metavar="PID", help="적용할 패턴 id 목록")
    ap.add_argument("--out", help="apply 결과 저장 경로 (기본: <md_stem>_stripped.md)")
    ap.add_argument("--json", action="store_true", help="결과를 JSON 으로 출력")
    ap.add_argument("--list", action="store_true", help="정의된 패턴 목록만 출력")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    patterns = load_patterns()

    if args.list:
        if args.json:
            print(json.dumps({"patterns": patterns}, ensure_ascii=False, indent=2))
        else:
            print(f"정의된 패턴: {len(patterns)}개  ({PATTERNS_PATH})")
            for p in patterns:
                print(f"  - {p['id']}: {p['name']}")
                if p.get("description"):
                    print(f"      {p['description']}")
        return 0

    if not args.md:
        print("ERROR: <md> 인자가 필요합니다 (또는 --list 사용).", file=sys.stderr)
        return 1

    md = Path(args.md)
    if not md.exists():
        print(f"ERROR: file not found: {md}", file=sys.stderr)
        return 1

    if not patterns:
        if args.json:
            print(json.dumps({"status": "empty", "patterns": []}))
        else:
            print(f"[STRIP] 패턴 정의 없음 ({PATTERNS_PATH}) — skip")
        return 0

    if args.apply:
        out_path = Path(args.out) if args.out else stripped_path_for(md)
        if out_path.resolve() == md.resolve():
            print(f"ERROR: --out 경로가 원본과 같습니다. 원본은 보존됩니다: {md}", file=sys.stderr)
            return 1
        applied, unknown = apply_patterns(md, args.apply, patterns, out_path)
        if args.json:
            print(json.dumps({
                "status": "applied",
                "source": str(md),
                "output": str(out_path),
                "applied": applied,
                "unknown": unknown,
            }, ensure_ascii=False, indent=2))
        else:
            for u in unknown:
                print(f"[STRIP-WARN] 알 수 없는 패턴 id: {u}")
            for a in applied:
                if a["count"] > 0:
                    print(f"[STRIP-APPLY] {a['id']}: {a['count']} 곳 치환")
                else:
                    print(f"[STRIP-APPLY] {a['id']}: 매칭 없음 (변경 없음)")
            print(f"[STRIP-OUT] {out_path}")
        return 0

    text = md.read_text(encoding="utf-8")
    matches = find_matches(text, patterns)

    if args.json:
        print(json.dumps({
            "status": "ok",
            "total_patterns": len(patterns),
            "matches": matches,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"[STRIP] 패턴 정의: {len(patterns)}개, 매칭된 패턴: {len(matches)}개")
        for m in matches:
            print(f"[STRIP-MATCH] kind={m['kind']} id={m['id']} ({m['count']} 곳): {m['name']}")
            if m.get("reason"):
                print(f"  reason: {m['reason']}")
            for s in m["samples"]:
                print(f"  L{s['line']}: {s['before']!r} -> {s['after']!r}")

    return 3 if matches else 0


if __name__ == "__main__":
    sys.exit(main())
