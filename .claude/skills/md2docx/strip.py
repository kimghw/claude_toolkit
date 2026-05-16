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
    python strip.py <md> --reference <docx>       # promote 패턴을 reference 의 heading numbering 정의에 따라 필터
    python strip.py <md> --json                   # 결과 JSON
    python strip.py <md> --apply <pid> [<pid>...] # 선택된 패턴 적용 → <md_stem>_stripped.md
    python strip.py <md> --apply <pid> --out X.md # 출력 경로 명시
    python strip.py --list                        # 정의된 패턴 목록만 보기

--reference 의 효과:
    promote-* 패턴은 reference docx 의 heading{N} 스타일에 numbering 이 실제 정의돼
    있을 때만 매칭으로 보고된다. 정의가 없으면 그 패턴은 건너뛴다 (사용자에게 잘못된
    질문을 던지지 않기 위함). 정의가 있으면 reason 에 실제 lvlText 포맷이 주입된다.

종료 코드:
    0 = 매칭 없음 또는 apply 성공
    1 = 실행 오류
    3 = 사용자 확인이 필요한 매칭 발견
"""

import argparse
import json
import re
import sys
import zipfile
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


def compile_pattern(p):
    return re.compile(p["pattern"], _parse_flags(p.get("flags")))


def get_passes(p):
    """한 패턴 항목의 (regex, replace) 리스트 반환.
    'passes' 배열이 있으면 그것을 사용, 없으면 단일 pattern/replace 로 single-pass."""
    if "passes" in p:
        return [
            (re.compile(s["pattern"], _parse_flags(s.get("flags"))), s["replace"])
            for s in p["passes"]
        ]
    return [(compile_pattern(p), p["replace"])]


HEADING_NAME_RE = re.compile(r"^heading\s+([1-9])$", re.IGNORECASE)


def inspect_heading_numbering(docx_path):
    """reference.docx 에서 heading 1~9 스타일에 정의된 numbering 의 lvlText 를 추출.

    Returns:
        dict {level (int 1-9): lvlText (str)}
        numbering 이 정의된 heading 레벨만 포함. 정의가 없으면 빈 dict.
    """
    try:
        with zipfile.ZipFile(docx_path) as z:
            styles_xml = z.read("word/styles.xml").decode("utf-8")
            try:
                numbering_xml = z.read("word/numbering.xml").decode("utf-8")
            except KeyError:
                numbering_xml = ""
    except (FileNotFoundError, zipfile.BadZipFile):
        return {}

    # 1) heading {N} 스타일에서 (numId, ilvl) 추출
    heading_to_num = {}  # {level: (numId, ilvl)}
    for m in re.finditer(r"<w:style\s+([^>]*?)>(.*?)</w:style>", styles_xml, re.DOTALL):
        attrs, body = m.group(1), m.group(2)
        if 'w:type="paragraph"' not in attrs:
            continue
        name_m = re.search(r'<w:name\s+w:val="([^"]+)"', body)
        if not name_m:
            continue
        h = HEADING_NAME_RE.match(name_m.group(1))
        if not h:
            continue
        level = int(h.group(1))
        numpr = re.search(r"<w:numPr>(.*?)</w:numPr>", body, re.DOTALL)
        if not numpr:
            continue
        nid = re.search(r'<w:numId\s+w:val="(\d+)"', numpr.group(1))
        ilvl = re.search(r'<w:ilvl\s+w:val="(\d+)"', numpr.group(1))
        if not nid:
            continue
        # numId="0" 은 numbering 제거 (Word 규약). 무시.
        if nid.group(1) == "0":
            continue
        heading_to_num[level] = (nid.group(1), int(ilvl.group(1)) if ilvl else 0)

    if not heading_to_num or not numbering_xml:
        return {}

    # 2) numbering.xml: numId → abstractNumId
    num_to_abstract = {}
    for m in re.finditer(
        r'<w:num\s+w:numId="(\d+)"[^>]*>(.*?)</w:num>', numbering_xml, re.DOTALL
    ):
        nid, body = m.group(1), m.group(2)
        a = re.search(r'<w:abstractNumId\s+w:val="(\d+)"', body)
        if a:
            num_to_abstract[nid] = a.group(1)

    # 3) abstractNumId + ilvl → lvlText
    abstract_lvl_text = {}  # {(abstractId, ilvl): lvlText}
    for m in re.finditer(
        r'<w:abstractNum\s+w:abstractNumId="(\d+)"[^>]*>(.*?)</w:abstractNum>',
        numbering_xml, re.DOTALL,
    ):
        aid, body = m.group(1), m.group(2)
        for lvl in re.finditer(r'<w:lvl\s+w:ilvl="(\d+)"[^>]*>(.*?)</w:lvl>', body, re.DOTALL):
            ilvl, lvl_body = int(lvl.group(1)), lvl.group(2)
            text = re.search(r'<w:lvlText\s+w:val="([^"]*)"', lvl_body)
            if text:
                abstract_lvl_text[(aid, ilvl)] = text.group(1)

    # 4) 합쳐서 {heading_level: lvlText}
    result = {}
    for level, (nid, ilvl) in heading_to_num.items():
        aid = num_to_abstract.get(nid)
        if not aid:
            continue
        lt = abstract_lvl_text.get((aid, ilvl))
        if lt is not None:
            result[level] = lt
    return result


def find_matches(text, patterns, heading_numbering=None):
    """패턴별 매칭 결과 반환.

    heading_numbering: {level: lvlText} 형태의 dict.
        promote 패턴이 target_heading_level 을 지정하면, 해당 레벨이 dict 에 없으면
        그 패턴은 결과에서 제외된다. 있으면 reason 에 실제 lvlText 가 주입된다.

    'passes' 배열을 가진 항목은 모든 패스의 매칭 합계를 보고하고, sample 은
    누적 적용 (앞 패스 결과를 다음 패스 입력으로) 결과를 보여준다.
    """
    results = []
    lines = text.split("\n")
    for p in patterns:
        target_level = p.get("target_heading_level")
        if p.get("kind") == "promote" and target_level is not None and heading_numbering is not None:
            if target_level not in heading_numbering:
                continue

        passes = get_passes(p)

        total_count = 0
        # 라인 단위 누적 sample 수집
        affected_lines = {}  # {line_no: (before, after_after_all_passes)}
        for regex, replace in passes:
            for m in regex.finditer(text):
                line_no = text.count("\n", 0, m.start()) + 1
                total_count += 1
                if line_no not in affected_lines:
                    affected_lines[line_no] = lines[line_no - 1]

        if total_count == 0:
            continue

        # 누적 sample 생성 (모든 passes 순차 적용 결과)
        samples = []
        for line_no in sorted(affected_lines)[:5]:
            before = affected_lines[line_no]
            after = before
            for regex, replace in passes:
                after = regex.sub(replace, after)
            samples.append({"line": line_no, "before": before, "after": after})

        reason = p.get("reason", "")
        if (
            p.get("kind") == "promote"
            and target_level is not None
            and heading_numbering
            and target_level in heading_numbering
        ):
            reason = (
                f"{reason} [reference 의 heading {target_level} 실제 lvlText: "
                f"'{heading_numbering[target_level]}']"
            )

        results.append({
            "id": p["id"],
            "kind": p.get("kind", "remove"),
            "name": p["name"],
            "description": p.get("description", ""),
            "reason": reason,
            "target_heading_level": target_level,
            "count": total_count,
            "samples": samples,
        })
    return results


def apply_patterns(md_path, pattern_ids, patterns, out_path):
    """원본 md_path 는 읽기 전용. 치환 결과는 out_path 로 저장.
    'passes' 배열을 가진 항목은 모든 패스를 순차 적용한다."""
    text = md_path.read_text(encoding="utf-8")
    by_id = {p["id"]: p for p in patterns}
    applied = []
    unknown = []
    for pid in pattern_ids:
        p = by_id.get(pid)
        if not p:
            unknown.append(pid)
            continue
        total = 0
        for regex, replace in get_passes(p):
            text, n = regex.subn(replace, text)
            total += n
        applied.append({"id": pid, "count": total})

    out_path.write_text(text, encoding="utf-8")
    return applied, unknown


def main():
    ap = argparse.ArgumentParser(description="회사 양식 충돌 패턴 검출·치환")
    ap.add_argument("md", nargs="?", help="대상 markdown 파일 (원본은 수정되지 않음)")
    ap.add_argument("--apply", nargs="+", metavar="PID", help="적용할 패턴 id 목록")
    ap.add_argument("--out", help="apply 결과 저장 경로 (기본: <md_stem>_stripped.md)")
    ap.add_argument("--reference", metavar="DOCX", help="reference docx (promote 패턴을 heading numbering 정의에 따라 필터)")
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

    heading_numbering = None
    if args.reference:
        ref_path = Path(args.reference)
        if not ref_path.exists():
            print(f"ERROR: --reference 파일 없음: {ref_path}", file=sys.stderr)
            return 1
        heading_numbering = inspect_heading_numbering(ref_path)

    matches = find_matches(text, patterns, heading_numbering=heading_numbering)

    if args.json:
        print(json.dumps({
            "status": "ok",
            "total_patterns": len(patterns),
            "heading_numbering": heading_numbering,
            "matches": matches,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"[STRIP] 패턴 정의: {len(patterns)}개, 매칭된 패턴: {len(matches)}개")
        if heading_numbering is not None:
            if heading_numbering:
                fmt = ", ".join(f"h{k}={v!r}" for k, v in sorted(heading_numbering.items()))
                print(f"[STRIP-HEADING-NUM] reference 의 heading numbering: {fmt}")
            else:
                print(f"[STRIP-HEADING-NUM] reference 의 heading 스타일에 numbering 정의 없음 (promote 패턴 자동 제외됨)")
        for m in matches:
            print(f"[STRIP-MATCH] kind={m['kind']} id={m['id']} ({m['count']} 곳): {m['name']}")
            if m.get("reason"):
                print(f"  reason: {m['reason']}")
            for s in m["samples"]:
                print(f"  L{s['line']}: {s['before']!r} -> {s['after']!r}")

    return 3 if matches else 0


if __name__ == "__main__":
    sys.exit(main())
