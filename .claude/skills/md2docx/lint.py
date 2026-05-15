#!/usr/bin/env python3
"""
md2docx/lint.py — Pandoc 변환 전 Markdown 넘버링/헤딩 사전 검토

목적
====
회사 양식 docx로 변환하기 전, markdown 원본의 ordered list 넘버링과
heading 기호가 **모호한 경우**를 감지해 사용자에게 확인할 수 있도록 한다.

  - 넘버링 혼용:   `1.`, `2.`, `3.` vs `1.`, `1.`, `1.` vs `1)`, `2)` 등
  - bullet 혼용:   `-`, `*`, `+` 가 같은 문서에 섞여 있음
  - heading 혼용:  atx (`# Title`) vs setext (`Title\n=====`)
  - heading 비순차: h1 → h3 처럼 레벨 건너뜀
  - h1 다수:        하나의 문서에 `# H1` 이 여러 번

검사 방식
=========
1) markdownlint-cli2 또는 markdownlint(-cli) 가 설치돼 있으면 그것을 호출
2) pymarkdownlnt (Python `pymarkdown`) 가 있으면 그것을 호출
3) 위 모두 없으면 내장 정규식 fallback 으로 위 5종을 자체 검사

Usage
=====
    python lint.py <input.md>
    python lint.py <input.md> --json
    python lint.py <input.md> --tool builtin   # 외부 도구 무시, 내장만 사용

종료 코드
=========
    0 = 문제 없음
    1 = 실행 오류 (파일 없음 등)
    2 = 사용자 확인이 필요한 모호한 넘버링/헤딩 감지
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


AMBIGUOUS_RULES = {
    "MD001": "heading-increment",
    "MD003": "heading-style",
    "MD004": "ul-style",
    "MD025": "single-h1",
    "MD029": "ol-prefix",
    "MD030": "list-marker-space",
}


def _decode(b):
    return b.decode("utf-8", errors="replace") if isinstance(b, (bytes, bytearray)) else b


# ---------------------------------------------------------------------------
# 외부 도구 디스패치
# ---------------------------------------------------------------------------

def find_external_tool():
    for cand in ("markdownlint-cli2", "markdownlint"):
        if shutil.which(cand):
            return cand
    if shutil.which("pymarkdown"):
        return "pymarkdown"
    return None


def run_external(tool, md_path):
    """외부 도구 호출 후 issues 리스트 반환. 각 item: {rule, line, desc}."""
    if tool == "pymarkdown":
        result = subprocess.run(
            ["pymarkdown", "scan", str(md_path)],
            capture_output=True,
        )
        text = _decode(result.stdout) + _decode(result.stderr)
        return parse_pymarkdown(text)

    if tool == "markdownlint":
        result = subprocess.run(
            [tool, "--json", str(md_path)],
            capture_output=True,
        )
        text = _decode(result.stdout) + _decode(result.stderr)
        try:
            data = json.loads(text)
            return [
                {
                    "rule": (it.get("ruleNames") or ["?"])[0],
                    "line": it.get("lineNumber"),
                    "desc": it.get("ruleDescription", ""),
                }
                for it in data
            ]
        except json.JSONDecodeError:
            return parse_textual(text)

    # markdownlint-cli2 — 기본 출력이 텍스트, stderr로 나옴
    result = subprocess.run(
        [tool, str(md_path)],
        capture_output=True,
    )
    text = _decode(result.stdout) + _decode(result.stderr)
    return parse_textual(text)


def parse_textual(text):
    """`file:line[:col] MDxxx/rule description` 형식 파싱."""
    issues = []
    pat = re.compile(
        r"^.*?:(?P<line>\d+)(?::\d+)?\s+(?P<rule>MD\d{3})(?:/[\w-]+)?\s+(?P<desc>.+)$",
        re.MULTILINE,
    )
    for m in pat.finditer(text):
        issues.append({
            "rule": m.group("rule"),
            "line": int(m.group("line")),
            "desc": m.group("desc").strip(),
        })
    return issues


def parse_pymarkdown(text):
    """`file:line:col: MDxxx: desc` 형식 파싱."""
    issues = []
    pat = re.compile(
        r"^.*?:(?P<line>\d+):\d+:\s+(?P<rule>MD\d{3}):\s+(?P<desc>.+)$",
        re.MULTILINE,
    )
    for m in pat.finditer(text):
        issues.append({
            "rule": m.group("rule"),
            "line": int(m.group("line")),
            "desc": m.group("desc").strip(),
        })
    return issues


# ---------------------------------------------------------------------------
# 내장 fallback 검사 (외부 도구 없을 때)
# ---------------------------------------------------------------------------

ATX_RE = re.compile(r"^(#{1,6})\s+\S")
SETEXT_RE = re.compile(r"^(=+|-+)\s*$")
UL_RE = re.compile(r"^\s*([-*+])\s+\S")
OL_RE = re.compile(r"^\s*(\d+)([.)])\s+\S")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def builtin_lint(md_path):
    """외부 도구 없이 핵심 모호성만 자체 검출."""
    text = Path(md_path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    issues = []
    in_fence = False
    bullet_chars = {}        # char -> first_line
    ol_styles = {}           # ('.' or ')') -> first_line
    ol_sequences = []        # 같은 레벨 ol 묶음 추적
    headings = []            # (line, level, style)

    prev_blank = True
    for i, raw in enumerate(lines, start=1):
        if FENCE_RE.match(raw):
            in_fence = not in_fence
            prev_blank = False
            continue
        if in_fence:
            prev_blank = False
            continue

        # ATX heading
        m = ATX_RE.match(raw)
        if m:
            headings.append((i, len(m.group(1)), "atx"))
            prev_blank = False
            continue

        # Setext heading: 이전 줄이 비어있지 않고 텍스트, 현재 줄이 = 또는 -
        if i >= 2 and SETEXT_RE.match(raw) and lines[i - 2].strip() and not ATX_RE.match(lines[i - 2]):
            level = 1 if raw.lstrip().startswith("=") else 2
            headings.append((i - 1, level, "setext"))
            prev_blank = False
            continue

        m = UL_RE.match(raw)
        if m:
            ch = m.group(1)
            bullet_chars.setdefault(ch, i)
            prev_blank = False
            continue

        m = OL_RE.match(raw)
        if m:
            num = int(m.group(1))
            sep = m.group(2)
            ol_styles.setdefault(sep, i)
            if not ol_sequences or ol_sequences[-1]["end_line"] != i - 1:
                ol_sequences.append({"start_line": i, "end_line": i, "nums": [num]})
            else:
                ol_sequences[-1]["end_line"] = i
                ol_sequences[-1]["nums"].append(num)
            prev_blank = False
            continue

        prev_blank = (raw.strip() == "")

    # MD004 — bullet 기호 혼용
    if len(bullet_chars) > 1:
        chars = sorted(bullet_chars.items(), key=lambda kv: kv[1])
        first_line = chars[0][1]
        issues.append({
            "rule": "MD004",
            "line": first_line,
            "desc": f"Unordered list style 혼용: {', '.join(repr(c) for c, _ in chars)}",
        })

    # MD029 — ordered list 번호 스타일 혼용 + 시퀀스 일관성
    if len(ol_styles) > 1:
        items = sorted(ol_styles.items(), key=lambda kv: kv[1])
        issues.append({
            "rule": "MD029",
            "line": items[0][1],
            "desc": f"Ordered list 구분자 혼용: {', '.join(repr(s) for s, _ in items)}",
        })
    for seq in ol_sequences:
        nums = seq["nums"]
        if len(nums) < 2:
            continue
        all_one = all(n == 1 for n in nums)
        sequential = all(nums[k] == nums[0] + k for k in range(len(nums)))
        if not (all_one or sequential):
            issues.append({
                "rule": "MD029",
                "line": seq["start_line"],
                "desc": f"Ordered list 번호 비일관: {nums} (모두 1 또는 순차여야 함)",
            })

    # MD003 — heading 스타일 혼용
    styles = {h[2] for h in headings}
    if len(styles) > 1:
        first = next(h for h in headings if h[2] != headings[0][2])
        issues.append({
            "rule": "MD003",
            "line": first[0],
            "desc": f"Heading 스타일 혼용: atx + setext (서로 다른 표현이 같은 문서에 존재)",
        })

    # MD025 — h1 다수
    h1s = [h for h in headings if h[1] == 1]
    if len(h1s) > 1:
        issues.append({
            "rule": "MD025",
            "line": h1s[1][0],
            "desc": f"Top-level heading(#) 가 {len(h1s)}개 — 문서당 1개 권장",
        })

    # MD001 — heading 레벨 비순차
    prev_level = 0
    for line_no, level, _ in headings:
        if prev_level and level > prev_level + 1:
            issues.append({
                "rule": "MD001",
                "line": line_no,
                "desc": f"Heading 레벨 건너뜀: h{prev_level} → h{level}",
            })
        prev_level = level

    return issues


# ---------------------------------------------------------------------------
# 분류
# ---------------------------------------------------------------------------

def classify(issues):
    ambiguous, other = [], []
    for it in issues:
        rule = it.get("rule", "")
        if rule in AMBIGUOUS_RULES:
            ambiguous.append({**it, "name": AMBIGUOUS_RULES[rule]})
        else:
            other.append(it)
    return ambiguous, other


def main():
    ap = argparse.ArgumentParser(description="Markdown 넘버링/헤딩 사전 검토")
    ap.add_argument("md", help="검사할 .md 파일")
    ap.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    ap.add_argument(
        "--tool",
        choices=("auto", "builtin"),
        default="auto",
        help="auto=외부 도구 우선, builtin=내장 fallback만 사용",
    )
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    md_path = Path(args.md)
    if not md_path.exists():
        print(f"ERROR: file not found: {md_path}", file=sys.stderr)
        return 1

    tool_used = "builtin"
    if args.tool == "auto":
        ext = find_external_tool()
        if ext:
            try:
                issues = run_external(ext, md_path)
                tool_used = ext
            except Exception as e:
                print(f"[LINT-WARN] 외부 도구({ext}) 실행 실패, 내장으로 대체: {e}", file=sys.stderr)
                issues = builtin_lint(md_path)
        else:
            issues = builtin_lint(md_path)
    else:
        issues = builtin_lint(md_path)

    ambiguous, other = classify(issues)

    if args.json:
        print(json.dumps({
            "status": "ok",
            "tool": tool_used,
            "ambiguous": ambiguous,
            "other": other,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"[LINT] tool={tool_used}, total={len(issues)}, ambiguous={len(ambiguous)}, other={len(other)}")
        for it in ambiguous:
            print(f"[LINT-AMBIGUOUS] L{it['line']} {it['rule']}({it.get('name', '')}): {it['desc']}")
        for it in other:
            print(f"[LINT-INFO] L{it['line']} {it['rule']}: {it['desc']}")

    return 2 if ambiguous else 0


if __name__ == "__main__":
    sys.exit(main())
