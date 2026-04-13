#!/usr/bin/env python3
"""md2wu Stage 1-2: Heading extraction + Token measurement.

Usage:
    python stage12_heading_tokens.py <md_file> <doc_instance_key> <document_key> <output_dir>

Example:
    python stage12_heading_tokens.py /path/to/ur-z3rev8.md ur_z3_rev8_en ur_z3 /path/to/results/temp/pre

Output:
    doc-{doc_instance_key}__heading__structure.tsv
"""

import re
import sys
import os

def get_encoder():
    """Get tiktoken encoder, fallback to char_approx."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return enc.encode, "tiktoken"
    except ImportError:
        def char_approx(text):
            import math
            return math.ceil(len(text) / 4 * 1.1)
        return lambda text: [0] * char_approx(text), "char_approx"


def parse_headings(lines):
    """Parse markdown headings, ignoring code blocks."""
    headings = []
    in_code_block = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        m = re.match(r'^(#{1,6})\s+(.+)$', stripped)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            headings.append({
                "level": level,
                "start_line": i + 1,  # 1-based
                "title": title,
            })
    return headings


def build_tree(headings, total_lines):
    """Set end_line and parent_id for each heading."""
    for i, h in enumerate(headings):
        # end_line: line before next heading of same or higher level, or file end
        end_line = total_lines
        for j in range(i + 1, len(headings)):
            if headings[j]["level"] <= h["level"]:
                end_line = headings[j]["start_line"] - 1
                break
        h["end_line"] = end_line

        # parent_id: nearest preceding heading with lower level number
        h["parent_id"] = ""
        for j in range(i - 1, -1, -1):
            if headings[j]["level"] < h["level"]:
                h["parent_id"] = headings[j].get("heading_id", "")
                break

    return headings


def measure_tokens(headings, lines, encode_fn):
    """Calculate inclusive and exclusive tokens for each heading."""
    for h in headings:
        # Inclusive: full span [start_line, end_line]
        span_text = "\n".join(lines[h["start_line"] - 1 : h["end_line"]])
        h["est_tokens_inclusive"] = len(encode_fn(span_text))

        # Exclusive: own content only (before first child heading)
        excl_end = h["end_line"]
        for other in headings:
            if other.get("parent_id") == h["heading_id"] and other["start_line"] > h["start_line"]:
                excl_end = other["start_line"] - 1
                break
        excl_text = "\n".join(lines[h["start_line"] - 1 : excl_end])
        h["est_tokens_exclusive"] = len(encode_fn(excl_text))

    return headings


def verify_additivity(headings):
    """Verify parent.Exclusive + sum(children.Inclusive) = parent.Inclusive."""
    errors = []
    hmap = {h["heading_id"]: h for h in headings}
    for h in headings:
        children = [c for c in headings if c["parent_id"] == h["heading_id"]]
        if children:
            expected = h["est_tokens_exclusive"] + sum(c["est_tokens_inclusive"] for c in children)
            if expected != h["est_tokens_inclusive"]:
                errors.append(
                    f"{h['heading_id']}: excl({h['est_tokens_exclusive']}) + "
                    f"children_incl({sum(c['est_tokens_inclusive'] for c in children)}) = "
                    f"{expected} != incl({h['est_tokens_inclusive']})"
                )
    return errors


def main():
    if len(sys.argv) < 5:
        print(f"Usage: {sys.argv[0]} <md_file> <doc_instance_key> <document_key> <output_dir>")
        sys.exit(1)

    md_file = sys.argv[1]
    doc_instance_key = sys.argv[2]
    document_key = sys.argv[3]
    output_dir = sys.argv[4]

    with open(md_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    lines = [l.rstrip("\n") for l in lines]
    total_lines = len(lines)

    encode_fn, measure_method = get_encoder()

    # Parse headings
    headings = parse_headings(lines)
    if not headings:
        print(f"WARNING: No headings found in {md_file}")
        # Create single entry for headingless doc
        full_text = "\n".join(lines)
        tokens = len(encode_fn(full_text))
        headings = [{
            "level": 1,
            "start_line": 1,
            "end_line": total_lines,
            "title": "(no heading)",
            "parent_id": "",
            "heading_id": f"{document_key}_HD_001",
            "est_tokens_inclusive": tokens,
            "est_tokens_exclusive": tokens,
        }]
    else:
        # Assign heading IDs
        for idx, h in enumerate(headings):
            h["heading_id"] = f"{document_key}_HD_{idx + 1:03d}"

        # Build tree (end_line, parent_id)
        headings = build_tree(headings, total_lines)

        # Measure tokens
        headings = measure_tokens(headings, lines, encode_fn)

    # Verify additivity
    errors = verify_additivity(headings)
    if errors:
        print(f"ADDITIVITY ERRORS in {doc_instance_key}:")
        for e in errors:
            print(f"  {e}")
    else:
        print(f"OK: {doc_instance_key} — {len(headings)} headings, "
              f"{headings[0]['est_tokens_inclusive']} tokens, "
              f"additivity PASS, measure={measure_method}")

    # Write TSV
    os.makedirs(output_dir, exist_ok=True)
    tsv_path = os.path.join(output_dir, f"doc-{doc_instance_key}__heading__structure.tsv")
    with open(tsv_path, "w", encoding="utf-8") as f:
        f.write("Heading_ID\tLevel\tStart_Line\tEnd_Line\tTitle\tParent_ID\t"
                "Est_Tokens_Inclusive\tEst_Tokens_Exclusive\n")
        for h in headings:
            f.write(f"{h['heading_id']}\t{h['level']}\t{h['start_line']}\t{h['end_line']}\t"
                    f"{h['title']}\t{h['parent_id']}\t"
                    f"{h['est_tokens_inclusive']}\t{h['est_tokens_exclusive']}\n")

    print(f"  Written: {tsv_path}")


if __name__ == "__main__":
    main()
