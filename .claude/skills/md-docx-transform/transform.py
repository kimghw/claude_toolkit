#!/usr/bin/env python3
"""
md-docx-transform: Markdown -> DOCX 변환 + tblLook 자동 보정 + 검증 리포트

Usage:
  python transform.py --md input.md --ref template.docx --out output.docx
  python transform.py --md input.md --ref template.dotx --out output.docx
  python transform.py --md input.md --ref template.docx --out output.docx --dry-run
"""
from __future__ import annotations
import argparse
import importlib.util as _importlib_util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections import OrderedDict

# Load sibling clone_table_props.py as a module (works whether or not the
# skill dir is on sys.path).
_SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
_CTP_PATH = os.path.join(_SKILL_DIR, "clone_table_props.py")
_ctp_spec = _importlib_util.spec_from_file_location("clone_table_props", _CTP_PATH)
clone_table_props = _importlib_util.module_from_spec(_ctp_spec)
_ctp_spec.loader.exec_module(clone_table_props)

# Force UTF-8 stdout so Korean / special chars work on Windows cp949 consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# ---------- tblStylePr type -> tblLook attribute mapping ----------
# Activation condition: for *Row/Col attributes the flag must be "1".
# For noHBand/noVBand it must be "0" (meaning banding is NOT suppressed).
TBLLOOK_MAP = {
    "firstRow":    ("w:firstRow",    "1"),
    "lastRow":     ("w:lastRow",     "1"),
    "firstCol":    ("w:firstColumn", "1"),
    "lastCol":     ("w:lastColumn",  "1"),
    "band1Horz":   ("w:noHBand",     "0"),
    "band2Horz":   ("w:noHBand",     "0"),
    "band1Vert":   ("w:noVBand",     "0"),
    "band2Vert":   ("w:noVBand",     "0"),
}

# Bitfield decoding for <w:tblLook w:val="XXXX" /> (hex), used when individual
# attributes are absent. Per ECMA-376.
TBLLOOK_BITS = {
    0x0020: "w:firstRow",
    0x0040: "w:lastRow",
    0x0080: "w:firstColumn",
    0x0100: "w:lastColumn",
    0x0200: "w:noHBand",
    0x0400: "w:noVBand",
}


def read_zip_text(zpath: str, name: str) -> str:
    with zipfile.ZipFile(zpath) as z:
        return z.read(name).decode("utf-8")


def find_style(xml: str, style_id: str) -> str | None:
    m = re.search(
        r'<w:style\b[^>]*w:styleId="' + re.escape(style_id) + r'"[^>]*>.*?</w:style>',
        xml, re.S)
    return m.group(0) if m else None


def get_basedOn(style_xml: str) -> str | None:
    m = re.search(r'<w:basedOn w:val="([^"]+)"', style_xml)
    return m.group(1) if m else None


def collect_tblstylepr_types(xml: str, start_style_id: str, visited=None) -> set[str]:
    """Walk basedOn chain and collect all tblStylePr types."""
    if visited is None:
        visited = set()
    if start_style_id in visited:
        return set()
    visited.add(start_style_id)
    style = find_style(xml, start_style_id)
    if not style:
        return set()
    types = set(re.findall(r'<w:tblStylePr w:type="([^"]+)"', style))
    parent = get_basedOn(style)
    if parent:
        types |= collect_tblstylepr_types(xml, parent, visited)
    return types


def parse_tbllook(tbllook_xml: str) -> dict[str, str]:
    """Return dict of tblLook attributes. Expand w:val bitfield if present."""
    attrs = dict(re.findall(r'(w:[a-zA-Z]+)="([^"]+)"', tbllook_xml))
    if "w:val" in attrs:
        try:
            val = int(attrs["w:val"], 16)
            for bit, name in TBLLOOK_BITS.items():
                # Bitfield semantics: bit SET means the conditional formatting
                # flag is ENABLED (for first/last) or DISABLED (for noHBand/noVBand).
                # Per OOXML spec. We only fill in attrs that are missing.
                if name not in attrs:
                    attrs[name] = "1" if (val & bit) else "0"
        except ValueError:
            pass
    return attrs


def determine_required_flags(template_types: set[str]) -> dict[str, str]:
    """From tblStylePr types, compute target tblLook attribute values."""
    required: dict[str, str] = {}
    for t in template_types:
        if t in TBLLOOK_MAP:
            attr, val = TBLLOOK_MAP[t]
            # Only upgrade (never weaken). For attrs that need "1", overwrite
            # if current is missing/"0". For noHBand/noVBand (need "0"),
            # the desired value is "0" which is Pandoc's default anyway — skip.
            if val == "1":
                required[attr] = "1"
            else:
                required[attr] = "0"
    return required


def fix_tbllook_in_doc(doc_xml: str, required: dict[str, str]) -> tuple[str, list[dict]]:
    """Walk each <w:tblLook ... /> and apply required flags. Returns new xml + changelog."""
    changes: list[dict] = []
    def repl(m: re.Match) -> str:
        original = m.group(0)
        attrs = parse_tbllook(original)
        before = dict(attrs)
        modified = False
        for attr, val in required.items():
            if attrs.get(attr) != val:
                attrs[attr] = val
                modified = True
        if not modified:
            return original
        # Rebuild. Drop w:val (stale bitfield) and write each known attr explicitly.
        attrs.pop("w:val", None)
        ordered_keys = [
            "w:firstRow", "w:lastRow", "w:firstColumn", "w:lastColumn",
            "w:noHBand", "w:noVBand",
        ]
        parts = []
        for k in ordered_keys:
            if k in attrs:
                parts.append(f'{k}="{attrs[k]}"')
        new = "<w:tblLook " + " ".join(parts) + "/>"
        changes.append({"before": before, "after": attrs})
        return new
    new_xml = re.sub(r'<w:tblLook\b[^/>]*/?>', repl, doc_xml)
    return new_xml, changes


def collect_orphan_refs(doc_xml: str, styles_xml: str) -> dict[str, list[str]]:
    """Find style references in document.xml that have no definition in styles.xml."""
    defined = set(re.findall(r'<w:style\b[^>]*w:styleId="([^"]+)"', styles_xml))
    orphans = {"pStyle": [], "rStyle": [], "tblStyle": []}
    for kind in orphans:
        refs = set(re.findall(r'<w:' + kind + r' w:val="([^"]+)"', doc_xml))
        missing = sorted(refs - defined)
        orphans[kind] = missing
    return orphans


def normalize_template(ref_path: str, tmpdir: str) -> str:
    """If template is .dotx, copy to a .docx inside tmpdir (pandoc only accepts .docx).
    Returns the usable .docx path.
    """
    ext = os.path.splitext(ref_path)[1].lower()
    if ext == ".docx":
        return ref_path
    if ext == ".dotx":
        dst = os.path.join(tmpdir, "_ref.docx")
        shutil.copy2(ref_path, dst)
        print(f"[0b]   .dotx detected -> copied to temp .docx: {dst}")
        return dst
    raise SystemExit(f"Unsupported template extension: {ext} (expect .docx or .dotx)")


def preflight_template(ref_docx: str) -> list[str]:
    """Check minimum template readiness. Return list of warnings (empty = OK).
    Does NOT fix anything — surfaces issues for the agent to resolve via
    extract-docx-styles before proceeding.
    """
    warnings = []
    styles = read_zip_text(ref_docx, "word/styles.xml")
    # Required Pandoc w:name presences
    must_have_names = ["Normal", "heading 1"]
    for nm in must_have_names:
        if not re.search(r'<w:name w:val="' + re.escape(nm) + r'"\s*/>', styles):
            warnings.append(f"Missing Pandoc-required w:name: {nm!r}")
    # Table style presence (required for Markdown table formatting)
    if not re.search(r'<w:name w:val="Table"\s*/>', styles):
        warnings.append(
            "Missing w:name='Table' — Markdown tables will render without style. "
            "Run extract-docx-styles to add it."
        )
    return warnings


def run_pandoc(md: str, ref: str, out: str, pandoc_path: str | None = None) -> None:
    cmd = [pandoc_path or "pandoc", md, f"--reference-doc={ref}", "-o", out]
    print(f"        cmd: {' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"pandoc failed:\n{proc.stderr}")
    print(f"        OK ({out}, {os.path.getsize(out)} bytes)")


def rewrite_docx_document_xml(docx_path: str, new_doc_xml: str) -> None:
    """Replace word/document.xml inside the .docx with new content (forward-slash safe)."""
    tmp = docx_path + ".tmp"
    with zipfile.ZipFile(docx_path, "r") as zin, \
         zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            if info.filename == "word/document.xml":
                new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
                new_info.compress_type = info.compress_type
                new_info.external_attr = info.external_attr
                zout.writestr(new_info, new_doc_xml.encode("utf-8"))
            else:
                new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
                new_info.compress_type = info.compress_type
                new_info.external_attr = info.external_attr
                zout.writestr(new_info, zin.read(info.filename))
    os.replace(tmp, docx_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--md", required=True, help="Input .md path")
    ap.add_argument("--ref", required=True, help="Word template (.docx or .dotx)")
    ap.add_argument("--out", required=True, help="Output .docx path")
    ap.add_argument("--pandoc", default=None, help="Pandoc executable path (defaults to PATH)")
    ap.add_argument("--dry-run", "--no-fix", action="store_true",
                    help="Skip all fixes (clone + tblLook); only report")
    ap.add_argument("--skip-preflight", action="store_true",
                    help="Skip template validation (use when extract-docx-styles has already run)")
    ap.add_argument("--no-clone-table", action="store_true",
                    help="Skip sample-table cloning; use legacy tblLook-only fix instead")
    ap.add_argument("--sample-index", type=int, default=None,
                    help="Which template table to use as sample (0-based, default 0). "
                         "If the template has multiple tables, the list is printed so the "
                         "caller can rerun with a specific index.")
    ap.add_argument("--override-jc", action="store_true",
                    help="Overwrite markdown :---:/---: alignment with sample/style's jc")
    ap.add_argument("--center-tables", action="store_true",
                    help="Inject <w:jc w:val='center'/> into each output table's tblPr "
                         "(centers the table itself on the page).")
    ap.add_argument("--verbose", action="store_true", help="More detailed output")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="md2docx_") as tmpdir:
        # 0. Template normalization (.dotx -> .docx temp copy) + preflight
        ref_docx = normalize_template(args.ref, tmpdir)

        if not args.skip_preflight:
            print("[0/3] Template preflight (Pandoc readiness check)...")
            warnings = preflight_template(ref_docx)
            if warnings:
                print("        Issues found — run `extract-docx-styles` on the template first:")
                for w in warnings:
                    print(f"          - {w}")
                print("        Continuing anyway (pass --skip-preflight to silence).")
            else:
                print("        OK — template has required Pandoc style names.")

        # 1. Run pandoc
        print("[1/3] Pandoc conversion...")
        run_pandoc(args.md, ref_docx, args.out, args.pandoc)

        # 2. Clone step (default) or legacy tblLook fix (--no-clone-table)
        tpl_styles = read_zip_text(ref_docx, "word/styles.xml")
        template_types = collect_tblstylepr_types(tpl_styles, "Table")
        return _continue(args, tpl_styles, template_types, ref_docx)


def _continue(args, tpl_styles, template_types, ref_docx: str):
    """Post-pandoc pipeline: clone sample-table formatting (or legacy tblLook fix),
    then report orphan style references."""
    print("[2/3] Apply template table formatting to output...")

    clone_result = None
    if not args.no_clone_table and not args.dry_run:
        clone_result = clone_table_props.clone_tables(
            template_docx=ref_docx,
            target_docx=args.out,
            sample_index=args.sample_index,
            override_jc=args.override_jc,
            center_tables=args.center_tables,
            verbose=args.verbose,
            print_prefix="        ",
        )
        if clone_result.get("cloned"):
            print(f"        → cloned sample[{clone_result['sample_index']}] "
                  f"(style chain: {'->'.join(clone_result.get('style_chain') or ['(none)'])}) "
                  f"onto {clone_result['tables_processed']} output table(s); "
                  f"{clone_result['rows']} rows, {clone_result['cells']} cells.")
        else:
            reason = clone_result.get("reason", "unknown")
            print(f"        → clone skipped ({reason}); falling back to legacy tblLook fix.")
            _legacy_tbllook_fix(args, template_types)
    elif args.no_clone_table:
        print("        (--no-clone-table) using legacy tblLook fix.")
        _legacy_tbllook_fix(args, template_types)
    else:
        print("        (--dry-run) skipping all fixes.")
        _legacy_tbllook_fix(args, template_types)  # prints report only

    # 3. Orphan style references
    out_doc = read_zip_text(args.out, "word/document.xml")
    out_styles = read_zip_text(args.out, "word/styles.xml")
    orphans = collect_orphan_refs(out_doc, out_styles)
    total = sum(len(v) for v in orphans.values())
    print("[3/3] Orphan style reference check...")
    if total:
        print("        Orphan style references (missing in template's styles.xml):")
        for kind, names in orphans.items():
            if names:
                print(f"          {kind:8s} {', '.join(names)}")
        print("        -> Consider re-running extract-docx-styles to add these.")
    else:
        print("        OK — all style references are defined in the template.")
    return 0


def _legacy_tbllook_fix(args, template_types: set[str]) -> None:
    """Pre-clone fallback: only patches <w:tblLook> flags (no cell pPr/tcPr).

    Used when --no-clone-table is set or when the template has no sample table.
    Prints mismatches and applies fix unless --dry-run.
    """
    required = determine_required_flags(template_types)
    out_doc = read_zip_text(args.out, "word/document.xml")
    tbl_looks = re.findall(r'<w:tblLook\b[^/>]*/?>', out_doc)
    mismatches = []
    for i, tl in enumerate(tbl_looks, 1):
        attrs = parse_tbllook(tl)
        bad = {k: (attrs.get(k), v) for k, v in required.items() if attrs.get(k) != v}
        if bad:
            mismatches.append((i, bad))
            if args.verbose:
                print(f"        Table {i}: MISMATCH {bad}")
    if not mismatches:
        print(f"        tblLook OK across {len(tbl_looks)} table(s).")
        return
    if args.dry_run:
        print(f"        DRY-RUN: would fix tblLook in {len(mismatches)} table(s).")
        return
    new_doc, changes = fix_tbllook_in_doc(out_doc, required)
    rewrite_docx_document_xml(args.out, new_doc)
    print(f"        Auto-fixed tblLook in {len(changes)} table(s).")


if __name__ == "__main__":
    sys.exit(main())
