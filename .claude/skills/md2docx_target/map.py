#!/usr/bin/env python3
"""
md2docx_target/map.py

target.docx (사용자 회사 양식 raw) 를 받아 Pandoc 어휘로 정규화된
reference docx 하나를 생성한다. 단일 기능 — md → docx 변환(convert) 은
하지 않는다.

원리:
    Pandoc 은 output docx 에 <w:pStyle w:val="Heading1"/> 같은 참조를 박는다.
    Word 는 reference 의 styles.xml 에서 매칭되는 w:name 으로 styleId 를
    찾아 그 스타일 정의를 적용한다.

    target 엔 보통 'heading 1'(소문자), 'Normal Table', 'Quote' 같은
    이름만 있고 Pandoc 이 요구하는 'Heading 1', 'Table', 'Block Text',
    'Source Code', 'Verbatim Char', 'Hyperlink' 등은 없다.

    이 스크립트는 target 의 기존 스타일을 그대로 두고, 그것을 basedOn 으로
    상속하는 새 스타일을 Pandoc 이름으로 추가해 reference 로 저장한다.

산출물(기본 — 작업 루트의 md2docx_target/ 폴더에 1쌍):
    <cwd>/md2docx_target/<target_stem>_template.docx
    <cwd>/md2docx_target/<target_stem>_template.report.md

    예: mydoc.docx → <cwd>/md2docx_target/mydoc_template.docx

Usage:
    python map.py <target.docx>                          # 기본: <cwd>/md2docx_target/<stem>_template.docx
    python map.py <target.docx> --out <path.docx>        # 출력 경로 명시
    python map.py <target.docx> --map mapping.json       # 사용자 map 오버라이드
    python map.py <target.docx> --report <path.md>       # 리포트 경로 명시
"""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent


PANDOC_STYLES = {
    "paragraph": {
        "critical": ["Normal", "Heading 1", "Heading 2", "Heading 3", "Source Code"],
        "important": ["Title", "Block Text", "Caption", "Heading 4", "Heading 5", "Heading 6"],
        "optional": [
            "Heading 7", "Heading 8", "Heading 9",
            "Body Text", "First Paragraph", "Compact",
            "Subtitle", "Author", "Date",
            "Abstract", "Abstract Title", "Bibliography",
            "Verbatim Code", "Footnote Text",
            "Image Caption", "Figure", "Captioned Figure",
            "TOC Heading",
            "toc 1", "toc 2", "toc 3", "toc 4", "toc 5",
            "toc 6", "toc 7", "toc 8", "toc 9",
        ],
    },
    "character": {
        "critical": ["Verbatim Char", "Hyperlink"],
        "important": ["Default Paragraph Font"],
        "optional": ["Footnote Reference"],
    },
    "table": {
        "critical": ["Table"],
        "important": [],
        "optional": [],
    },
}

# 의미 map 힌트 — Pandoc 개념 ↔ target 에 있을 법한 스타일 이름
SEMANTIC_HINTS = {
    ("paragraph", "Block Text"): ["Quote", "Intense Quote", "Blockquote", "인용"],
    ("paragraph", "Source Code"): ["Code", "Code Block", "Preformatted Text", "PreformattedText", "HTML Preformatted"],
    ("paragraph", "Caption"): ["Caption", "Image Caption", "Figure Caption", "Table Caption", "Caption Text"],
    ("paragraph", "Verbatim Code"): ["Code", "Code Block", "Preformatted Text"],
    ("paragraph", "Image Caption"): ["Image Caption", "Caption", "Figure Caption"],
    ("paragraph", "TOC Heading"): ["TOC Heading", "Table of Contents Heading", "목차 제목"],
    ("paragraph", "Body Text"): ["Body Text", "Body Text 1", "본문"],
    ("paragraph", "First Paragraph"): ["First Paragraph", "First Line"],
    ("paragraph", "Compact"): ["List Paragraph", "Compact"],
    ("paragraph", "Author"): ["Author", "Author Name"],
    ("paragraph", "Date"): ["Date"],
    ("paragraph", "Abstract"): ["Abstract"],
    ("character", "Verbatim Char"): ["Code Char", "Inline Code", "Code", "Source Code Char"],
    ("character", "Hyperlink"): ["Hyperlink", "Internet Link", "Link"],
    ("character", "Footnote Reference"): ["Footnote Reference", "Footnote Anchor"],
    ("table", "Table"): ["Table Grid", "Normal Table", "Table Normal", "Plain Table 1", "Grid Table"],
}

for i in range(1, 10):
    SEMANTIC_HINTS[("paragraph", f"toc {i}")] = [f"toc {i}", f"TOC {i}", f"heading {i}", f"Heading {i}"]


# target 에 없는 Pandoc 스타일에 대한 stub 정의. 결정 근거는 decisions.md.
STUB_DEFINITIONS = {
    ("character", "Verbatim Char"): {
        "props": '<w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/><w:shd w:val="clear" w:color="auto" w:fill="F2F2F2"/></w:rPr>',
        "note": "인라인 코드: 고정폭 폰트 (Consolas) + 회색 배경",
        "basedOn": None,
    },
    ("character", "Hyperlink"): {
        "props": '<w:rPr><w:color w:val="0563C1"/><w:u w:val="single"/></w:rPr>',
        "note": "링크: 파란색 + 밑줄 (Word 기본 Hyperlink와 동일)",
        "basedOn": None,
    },
    ("paragraph", "Source Code"): {
        "props": '<w:pPr><w:spacing w:before="120" w:after="120"/><w:ind w:left="360"/></w:pPr>'
                 '<w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/><w:sz w:val="20"/></w:rPr>',
        "note": "코드 블록: 고정폭 폰트 (Consolas 10pt) + 들여쓰기",
        "basedOn": "Normal",
    },
    ("paragraph", "Caption"): {
        "props": '<w:pPr><w:spacing w:before="120" w:after="120"/><w:jc w:val="center"/></w:pPr>'
                 '<w:rPr><w:i/><w:sz w:val="18"/></w:rPr>',
        "note": "캡션: 가운데 정렬 + 이탤릭 9pt",
        "basedOn": "Normal",
    },
    ("paragraph", "Footnote Text"): {
        "props": '<w:rPr><w:sz w:val="18"/></w:rPr>',
        "note": "각주 본문: 9pt",
        "basedOn": "Normal",
    },
    ("character", "Footnote Reference"): {
        "props": '<w:rPr><w:vertAlign w:val="superscript"/></w:rPr>',
        "note": "각주 번호: 윗첨자",
        "basedOn": None,
    },
    ("paragraph", "Image Caption"): {
        "props": '<w:pPr><w:spacing w:before="120" w:after="120"/><w:jc w:val="center"/></w:pPr>'
                 '<w:rPr><w:i/><w:sz w:val="18"/></w:rPr>',
        "note": "이미지 캡션: Caption과 동일",
        "basedOn": "Normal",
    },
    ("paragraph", "TOC Heading"): {
        "props": '<w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>'
                 '<w:rPr><w:b/><w:sz w:val="32"/></w:rPr>',
        "note": "목차 제목: 굵게 16pt",
        "basedOn": "Heading 1",
    },
}


# ---------------------------------------------------------------------------
# styles.xml 파싱
# ---------------------------------------------------------------------------

def extract_styles(styles_xml_content):
    pattern = re.compile(r"<w:style\s+([^>]*?)>(.*?)</w:style>", re.DOTALL)
    styles = []
    for m in pattern.finditer(styles_xml_content):
        attrs, body = m.group(1), m.group(2)
        sid = re.search(r'w:styleId="([^"]+)"', attrs)
        stype = re.search(r'w:type="([^"]+)"', attrs)
        default = re.search(r'w:default="([^"]+)"', attrs)
        name_m = re.search(r'<w:name\s+w:val="([^"]+)"', body)
        based_m = re.search(r'<w:basedOn\s+w:val="([^"]+)"', body)
        styles.append({
            "id": sid.group(1) if sid else "",
            "type": stype.group(1) if stype else "",
            "default": (default.group(1) == "1") if default else False,
            "name": name_m.group(1) if name_m else "",
            "basedOn": based_m.group(1) if based_m else "",
        })
    return styles


def extract_numbering(docx_path):
    try:
        with zipfile.ZipFile(docx_path) as z:
            content = z.read("word/numbering.xml").decode("utf-8")
    except (KeyError, FileNotFoundError, zipfile.BadZipFile):
        return []
    results = []
    for m in re.finditer(
        r'<w:abstractNum\s+w:abstractNumId="(\d+)"[^>]*>(.*?)</w:abstractNum>',
        content, re.DOTALL,
    ):
        aid, body = m.group(1), m.group(2)
        lvls = re.findall(r'<w:lvl\s+w:ilvl="(\d+)"[^>]*>(.*?)</w:lvl>', body, re.DOTALL)
        if not lvls:
            continue
        levels = []
        for ilvl, lvl_body in lvls[:3]:
            fmt = re.search(r'<w:numFmt\s+w:val="([^"]+)"', lvl_body)
            text = re.search(r'<w:lvlText\s+w:val="([^"]+)"', lvl_body)
            levels.append({
                "lvl": ilvl,
                "fmt": fmt.group(1) if fmt else "—",
                "text": text.group(1) if text else "—",
            })
        results.append({"id": aid, "levels": levels})
    return results


# ---------------------------------------------------------------------------
# map 결정 로직
# ---------------------------------------------------------------------------

def find_mapping(pandoc_name, stype, styles, user_overrides):
    if (stype, pandoc_name) in user_overrides:
        target = user_overrides[(stype, pandoc_name)]
        for s in styles:
            if s["type"] == stype and s["name"] == target:
                return ("user_override", s["id"], s["name"])
        return ("user_override_invalid", None, target)

    for s in styles:
        if s["type"] == stype and s["name"] == pandoc_name:
            return ("exact", s["id"], s["name"])

    for s in styles:
        if s["type"] == stype and s["name"].lower() == pandoc_name.lower():
            return ("case_mismatch", s["id"], s["name"])

    hints = SEMANTIC_HINTS.get((stype, pandoc_name), [])
    for hint in hints:
        for s in styles:
            if s["type"] == stype and s["name"] == hint:
                return ("semantic", s["id"], s["name"])
        for s in styles:
            if s["type"] == stype and s["name"].lower() == hint.lower():
                return ("semantic", s["id"], s["name"])

    return ("missing", None, None)


def make_unique_style_id(base, existing_ids):
    candidate = re.sub(r"[^A-Za-z0-9]", "", base)
    if not candidate:
        candidate = "PandocStyle"
    if candidate not in existing_ids:
        return candidate
    i = 1
    while f"{candidate}{i}" in existing_ids:
        i += 1
    return f"{candidate}{i}"


def compute_plan(styles, user_overrides):
    existing_ids = {s["id"] for s in styles}
    plan = []
    for stype, severities in PANDOC_STYLES.items():
        for severity, names in severities.items():
            for name in names:
                status, src_id, src_name = find_mapping(name, stype, styles, user_overrides)
                item = {
                    "pandoc_name": name,
                    "type": stype,
                    "severity": severity,
                    "status": status,
                    "source_id": src_id,
                    "source_name": src_name,
                    "new_style_id": None,
                    "stub": False,
                }
                if status in ("case_mismatch", "semantic", "user_override"):
                    item["new_style_id"] = make_unique_style_id(name, existing_ids)
                    existing_ids.add(item["new_style_id"])
                elif status == "missing" and (stype, name) in STUB_DEFINITIONS:
                    item["status"] = "stub"
                    item["stub"] = True
                    item["new_style_id"] = make_unique_style_id(name, existing_ids)
                    existing_ids.add(item["new_style_id"])
                plan.append(item)
    return plan


def find_basedon_id(basedon_name, stype, styles, plan):
    for p in plan:
        if p.get("new_style_id") and p["type"] == stype and p["pandoc_name"] == basedon_name:
            return p["new_style_id"]
    for s in styles:
        if s["type"] == stype and s["name"] == basedon_name:
            return s["id"]
    for s in styles:
        if s["type"] == stype and s["name"].lower() == basedon_name.lower():
            return s["id"]
    return None


# ---------------------------------------------------------------------------
# 새 스타일 XML 생성
# ---------------------------------------------------------------------------

def build_new_style_xml(plan_item):
    sid = plan_item["new_style_id"]
    stype = plan_item["type"]
    name = plan_item["pandoc_name"]
    basedon = plan_item["source_id"]
    return (
        f'<w:style w:type="{stype}" w:styleId="{sid}" w:customStyle="1">'
        f'<w:name w:val="{name}"/>'
        f'<w:basedOn w:val="{basedon}"/>'
        f'</w:style>'
    )


def build_stub_style_xml(plan_item, styles, plan):
    sid = plan_item["new_style_id"]
    stype = plan_item["type"]
    name = plan_item["pandoc_name"]
    stub_def = STUB_DEFINITIONS[(stype, name)]

    parts = [f'<w:style w:type="{stype}" w:styleId="{sid}" w:customStyle="1">']
    parts.append(f'<w:name w:val="{name}"/>')

    basedon_name = stub_def.get("basedOn")
    if basedon_name:
        basedon_id = find_basedon_id(basedon_name, stype, styles, plan)
        if basedon_id:
            parts.append(f'<w:basedOn w:val="{basedon_id}"/>')

    parts.append(stub_def["props"])
    parts.append("</w:style>")
    return "".join(parts)


def apply_mapping(input_docx, output_docx, plan, styles):
    with zipfile.ZipFile(input_docx) as zin:
        names = zin.namelist()
        contents = {n: zin.read(n) for n in names}

    styles_xml = contents["word/styles.xml"].decode("utf-8")

    new_blocks = []
    for item in plan:
        if item.get("new_style_id"):
            if item.get("stub"):
                new_blocks.append(build_stub_style_xml(item, styles, plan))
            else:
                new_blocks.append(build_new_style_xml(item))

    if new_blocks:
        insertion = "".join(new_blocks)
        if "</w:styles>" not in styles_xml:
            raise RuntimeError("styles.xml 구조가 예상과 다름 (closing tag 없음)")
        styles_xml = styles_xml.replace("</w:styles>", insertion + "</w:styles>")
        contents["word/styles.xml"] = styles_xml.encode("utf-8")

    output_docx.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_docx, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in names:
            zout.writestr(n, contents[n])

    return len(new_blocks)


# ---------------------------------------------------------------------------
# 리포트
# ---------------------------------------------------------------------------

def render_report(plan, styles, input_path, output_path, numbering):
    lines = []
    lines.append("# Style Mapping Plan")
    lines.append("")
    lines.append(f"- **Input (target)**: `{input_path}`")
    lines.append(f"- **Output (reference)**: `{output_path}`")
    lines.append(f"- **Template styles**: {len(styles)}")
    if numbering:
        lines.append(f"- **Numbering 정의**: {len(numbering)}개 발견 (참고용 — markdown 리스트는 Pandoc 기본 유지)")
    lines.append("")

    if numbering:
        lines.append("## target 의 Numbering 정의 (참고)")
        lines.append("")
        lines.append("target 에 정의된 list 번호 양식. 본 스킬은 회사 numbering 을 markdown 리스트에 자동 적용하지 않는다 — Pandoc 기본 양식 유지(decisions.md 결정 8).")
        lines.append("")
        lines.append("| abstractNumId | 레벨 | numFmt | 표시 텍스트 |")
        lines.append("|---|---|---|---|")
        for n in numbering:
            for lv in n["levels"]:
                lines.append(f"| {n['id']} | {lv['lvl']} | {lv['fmt']} | `{lv['text']}` |")
        lines.append("")

    by_status = {}
    for p in plan:
        by_status.setdefault(p["status"], []).append(p)

    lines.append("## Summary")
    lines.append("")
    lines.append("| 상태 | 개수 | 처리 |")
    lines.append("|---|---|---|")
    lines.append(f"| exact (이미 일치) | {len(by_status.get('exact', []))} | none |")
    lines.append(f"| case_mismatch (대소문자) | {len(by_status.get('case_mismatch', []))} | new style 추가 |")
    lines.append(f"| semantic match (의미 map) | {len(by_status.get('semantic', []))} | new style 추가 |")
    lines.append(f"| user_override | {len(by_status.get('user_override', []))} | new style 추가 |")
    lines.append(f"| stub (디폴트 생성) | {len(by_status.get('stub', []))} | stub style 생성 |")
    lines.append(f"| **missing (후보 없음)** | **{len(by_status.get('missing', []))}** | **skip** |")
    lines.append("")

    sections = [
        ("Case mismatch → 추가", ["case_mismatch"]),
        ("Semantic match → 추가", ["semantic"]),
        ("User override → 추가", ["user_override"]),
        ("Stub (target 에 없어 디폴트 생성)", ["stub"]),
        ("Missing (수동 처리 필요)", ["missing"]),
        ("Exact (변경 없음)", ["exact"]),
    ]
    for title, keys in sections:
        rows = [p for p in plan if p["status"] in keys]
        if not rows:
            continue
        lines.append(f"## {title}")
        lines.append("")
        if "stub" in keys:
            lines.append("| severity | Pandoc 이름 | type | new styleId | 적용 디폴트 |")
            lines.append("|---|---|---|---|---|")
            for r in rows:
                stub_def = STUB_DEFINITIONS.get((r["type"], r["pandoc_name"]), {})
                note = stub_def.get("note", "—")
                new = f"`{r['new_style_id']}`" if r.get("new_style_id") else "—"
                lines.append(f"| {r['severity']} | `{r['pandoc_name']}` | {r['type']} | {new} | {note} |")
        else:
            lines.append("| severity | Pandoc 이름 | type | source 스타일 | new styleId |")
            lines.append("|---|---|---|---|---|")
            for r in rows:
                src = f"`{r['source_name']}` (id=`{r['source_id']}`)" if r["source_id"] else "—"
                new = f"`{r['new_style_id']}`" if r.get("new_style_id") else "—"
                lines.append(f"| {r['severity']} | `{r['pandoc_name']}` | {r['type']} | {src} | {new} |")
        lines.append("")

    missing_critical = [p for p in by_status.get("missing", []) if p["severity"] == "critical"]
    if missing_critical:
        lines.append("## ⚠️ Critical 누락 — 수동 처리 필요")
        lines.append("")
        lines.append("아래 스타일은 target 에 의미적으로 대응되는 스타일이 없습니다.")
        lines.append("Word 에서 직접 생성하거나, `--map` 옵션으로 임의 map 을 지정해주세요.")
        lines.append("")
        for r in missing_critical:
            lines.append(f"- `{r['pandoc_name']}` ({r['type']})")
        lines.append("")
        lines.append("`--map` 파일 예시 (`mapping.json`):")
        lines.append("")
        lines.append("```json")
        sample = {}
        for r in missing_critical:
            sample.setdefault(r["type"], {})[r["pandoc_name"]] = "여기에_대응시킬_target_스타일_w:name"
        lines.append(json.dumps(sample, indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def default_output_path(target_path: Path) -> Path:
    """기본 산출물 경로 — <cwd>/md2docx_target/<target_stem>_template.docx.
    Pandoc 의 --reference-doc 입력이지만 사용자가 다루는 외부 이름은 "template" 으로 통일한다."""
    return Path.cwd() / "md2docx_target" / f"{target_path.stem}_template.docx"


def default_report_path(output_path: Path) -> Path:
    return output_path.with_suffix("").with_suffix(".report.md") if output_path.suffix == ".docx" \
        else output_path.with_name(output_path.stem + ".report.md")


def main():
    p = argparse.ArgumentParser(
        description="target.docx → <target_stem>_template.docx (Pandoc 호환 reference, 외부 이름은 template)",
    )
    p.add_argument("target", help="입력 target.docx (회사 양식 raw)")
    p.add_argument("--out", help="template 출력 경로 (기본: <cwd>/output_<target_stem>/templates/<target_stem>_template.docx)")
    p.add_argument("--report", help="리포트 출력 경로 (기본: <out>.report.md)")
    p.add_argument("--map", dest="map_json", metavar="MAPPING.json", help="사용자 map 오버라이드 JSON")
    args = p.parse_args()

    target_path = Path(args.target)
    if not target_path.exists():
        sys.exit(f"ERROR: not found: {target_path}")
    if target_path.suffix.lower() != ".docx":
        sys.exit(f"ERROR: target 은 .docx 여야 함: {target_path}")

    output_path = Path(args.out) if args.out else default_output_path(target_path)
    if not output_path.is_absolute():
        output_path = output_path.resolve()

    report_path = Path(args.report) if args.report else output_path.with_name(output_path.stem + ".report.md")
    if not report_path.is_absolute():
        report_path = report_path.resolve()

    user_overrides = {}
    if args.map_json:
        data = json.loads(Path(args.map_json).read_text(encoding="utf-8"))
        for stype, m in data.items():
            for pname, tname in m.items():
                user_overrides[(stype, pname)] = tname

    with zipfile.ZipFile(target_path) as z:
        styles_xml = z.read("word/styles.xml").decode("utf-8")

    styles = extract_styles(styles_xml)
    numbering = extract_numbering(target_path)
    plan = compute_plan(styles, user_overrides)

    added = apply_mapping(target_path, output_path, plan, styles)

    report = render_report(plan, styles, target_path, output_path, numbering)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print(f"[APPLY] {added} new styles added -> {output_path}")
    print(f"[REPORT] {report_path}")


if __name__ == "__main__":
    main()
