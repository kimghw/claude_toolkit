"""Clone a template's sample table formatting onto every table in a target .docx.

The template's sample table usually has NO direct per-cell formatting — its
appearance comes from a <w:tblStyle> reference whose definition (in styles.xml)
provides base pPr/tcPr plus conditional overlays (firstRow, firstCol, ...).
Pandoc output has orphan <w:pStyle> references that break that inheritance.

This script's approach: walk the sample's <w:tblStyle> basedOn chain, merge
base and per-region tblStylePr definitions, then materialize the *effective*
pPr/tcPr of each output cell as DIRECT formatting based on its position.
Result: no inheritance needed — the output renders as if Word had fully
applied the template's style.

Pipeline:
  1. Enumerate ALL <w:tbl> in the template (summary per table).
  2. Pick sample: if 1 table, use it automatically. If >1, default to index 0
     and print the list; user re-runs with --sample-index N if needed.
  3. Resolve the sample's <w:tblStyle> chain from styles.xml:
       - merge base <w:pPr>/<w:tcPr>/<w:trPr>/<w:tblPr> along basedOn chain
       - collect tblStylePr conditional regions (firstRow, firstCol, ...)
  4. Clone sample's <w:tblPr> and <w:tblGrid> (grid rebuilt to output col count).
  5. For every output cell at (row, col), compute effective pPr/tcPr by
     overlaying conditionals (wholeTable → bands → firstCol/lastCol →
     firstRow/lastRow → corner cells) in OOXML precedence order, then apply
     as direct formatting.
  6. Markdown's :---: / ---: alignment (<w:jc>) preserved unless --override-jc.

Usage:
  python clone_table_props.py --template T.docx --target OUT.docx
  python clone_table_props.py --template T.docx --target OUT.docx --sample-index 1
  python clone_table_props.py --template T.docx --target OUT.docx --list-only
  python clone_table_props.py --template T.docx --target OUT.docx --out FIXED.docx
  python clone_table_props.py --template T.docx --target OUT.docx --override-jc
"""
from __future__ import annotations

import argparse
import copy
import os
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


# ---------- namespaces ----------
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS_REG = {
    "w":   W_NS,
    "r":   "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "m":   "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "mc":  "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "wp":  "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a":   "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "v":   "urn:schemas-microsoft-com:vml",
    "o":   "urn:schemas-microsoft-com:office:office",
    "w10": "urn:schemas-microsoft-com:office:word",
}
for _p, _u in _NS_REG.items():
    ET.register_namespace(_p, _u)


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


# ---------- zip I/O ----------
def read_zip_text(zpath: str, name: str) -> str:
    with zipfile.ZipFile(zpath) as z:
        return z.read(name).decode("utf-8")


def rewrite_docx_part(docx_path: str, part_name: str, new_text: str) -> None:
    tmp = docx_path + ".tmp"
    with zipfile.ZipFile(docx_path, "r") as zin, \
         zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = new_text.encode("utf-8") if info.filename == part_name \
                   else zin.read(info.filename)
            new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            zout.writestr(new_info, data)
    os.replace(tmp, docx_path)


# ---------- property merging ----------
def merge_prop(base, override):
    """Merge `override` onto `base` (both Elements or None).

    Children of `override` replace same-tag children in `base`. Returns a new
    Element. None is treated as empty."""
    if override is None:
        return copy.deepcopy(base) if base is not None else None
    if base is None:
        return copy.deepcopy(override)
    result = copy.deepcopy(base)
    overlay_tags = {c.tag for c in override}
    for existing in list(result):
        if existing.tag in overlay_tags:
            result.remove(existing)
    for child in override:
        result.append(copy.deepcopy(child))
    return result


# ---------- style resolution ----------
def parse_styles(template_docx: str) -> dict:
    """Parse styles.xml → {styleId: {name, type, basedOn, pPr, tcPr, trPr, tblPr, tblStylePr{type:{...}}}}."""
    root = ET.fromstring(read_zip_text(template_docx, "word/styles.xml"))
    out = {}
    for s in root.findall(w("style")):
        sid = s.get(w("styleId"))
        if sid is None:
            continue
        def _attr(el, tag):
            e = s.find(tag)
            return e.get(w("val")) if e is not None else None
        out[sid] = {
            "name": _attr(s, w("name")),
            "type": s.get(w("type")),
            "basedOn": _attr(s, w("basedOn")),
            "pPr": s.find(w("pPr")),
            "tcPr": s.find(w("tcPr")),
            "trPr": s.find(w("trPr")),
            "tblPr": s.find(w("tblPr")),
            "tblStylePr": {
                tsp.get(w("type")): {
                    "pPr": tsp.find(w("pPr")),
                    "tcPr": tsp.find(w("tcPr")),
                    "trPr": tsp.find(w("trPr")),
                    "tblPr": tsp.find(w("tblPr")),
                }
                for tsp in s.findall(w("tblStylePr"))
                if tsp.get(w("type"))
            },
        }
    return out


def resolve_chain(styles: dict, start_id: str) -> dict:
    """Walk basedOn chain deepest-first. Returns merged base + tblStylePr region map.

    Merge order: ancestor's properties first, then each descendant overlays."""
    chain = []
    seen = set()
    cur = start_id
    while cur and cur in styles and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        cur = styles[cur]["basedOn"]

    merged = {"pPr": None, "tcPr": None, "trPr": None, "tblPr": None,
              "tblStylePr": {}}
    # ancestor-most first so descendants overlay
    for sid in reversed(chain):
        e = styles[sid]
        for k in ("pPr", "tcPr", "trPr", "tblPr"):
            merged[k] = merge_prop(merged[k], e[k])
        for t, block in e["tblStylePr"].items():
            cur_block = merged["tblStylePr"].setdefault(
                t, {"pPr": None, "tcPr": None, "trPr": None, "tblPr": None})
            for k in ("pPr", "tcPr", "trPr", "tblPr"):
                cur_block[k] = merge_prop(cur_block[k], block[k])
    return merged


# ---------- effective properties per cell ----------
# OOXML precedence order for tblStylePr regions (later overrides earlier).
_REGION_ORDER = (
    "wholeTable",
    "band1Horz", "band2Horz", "band1Vert", "band2Vert",
    "firstCol", "lastCol", "firstRow", "lastRow",
    "neCell", "nwCell", "seCell", "swCell",
)

# Bitfield decoding for <w:tblLook w:val="XXXX"/>, per ECMA-376.
_TBLLOOK_BITS = {
    0x0020: "firstRow",
    0x0040: "lastRow",
    0x0080: "firstColumn",
    0x0100: "lastColumn",
    0x0200: "noHBand",
    0x0400: "noVBand",
}


def _int_child_val(parent, child_tag: str, default: int = 1) -> int:
    """Read int from <w:child_tag w:val="N"/>. Returns default if missing/invalid."""
    if parent is None:
        return default
    child = parent.find(w(child_tag))
    if child is None:
        return default
    v = child.get(w("val"))
    if v is None:
        return default
    try:
        return int(v)
    except ValueError:
        return default


def parse_tbl_look(tblPr) -> dict:
    """Extract tblLook flags from a <w:tblPr>. Returns dict with 6 booleans.

    Defaults (when <w:tblLook> is absent): all False — no conditional overlays
    and no banding. When <w:tblLook> is present, individual attributes default
    to False per ECMA-376; bitfield `w:val` is also decoded."""
    flags = {"firstRow": False, "lastRow": False, "firstColumn": False,
             "lastColumn": False, "noHBand": False, "noVBand": False}
    if tblPr is None:
        return flags
    tl = tblPr.find(w("tblLook"))
    if tl is None:
        # tblLook entirely absent → treat bands as disabled too
        flags["noHBand"] = True
        flags["noVBand"] = True
        return flags
    for k in flags:
        v = tl.get(w(k))
        if v is not None:
            flags[k] = v == "1" or v.lower() == "true"
    val = tl.get(w("val"))
    if val:
        try:
            bits = int(val, 16)
            for mask, name in _TBLLOOK_BITS.items():
                if bits & mask:
                    flags[name] = True
        except ValueError:
            pass
    return flags


def applicable_regions(row_i: int, col_j: int, n_rows: int, n_cols: int,
                       style_regions: set | None = None,
                       look: dict | None = None,
                       row_band_size: int = 1,
                       col_band_size: int = 1) -> list[str]:
    """Which tblStylePr regions apply to cell (row_i, col_j).

    Horizontal/vertical bands are emitted only when (a) the style chain
    actually defines band1Horz/band2Horz/band1Vert/band2Vert, and (b) the
    effective <w:tblLook> does not suppress bands (noHBand/noVBand). The
    "body" range for banding excludes firstRow/lastRow (resp. firstCol/
    lastCol) whenever those regions are present in the style."""
    if style_regions is None:
        style_regions = set()
    if look is None:
        look = {"firstRow": False, "lastRow": False, "firstColumn": False,
                "lastColumn": False, "noHBand": True, "noVBand": True}

    fr, lr = row_i == 0, row_i == n_rows - 1
    fc, lc = col_j == 0, col_j == n_cols - 1

    has_firstRow = "firstRow" in style_regions
    has_lastRow  = "lastRow"  in style_regions
    has_firstCol = "firstCol" in style_regions
    has_lastCol  = "lastCol"  in style_regions

    regions = ["wholeTable"]

    h_bands = ("band1Horz" in style_regions) or ("band2Horz" in style_regions)
    if h_bands and not look.get("noHBand", False):
        body_start = 1 if has_firstRow else 0
        body_end   = n_rows - 1 if has_lastRow else n_rows
        if body_start <= row_i < body_end:
            rel = row_i - body_start
            band_idx = (rel // max(1, row_band_size)) % 2
            regions.append("band1Horz" if band_idx == 0 else "band2Horz")

    v_bands = ("band1Vert" in style_regions) or ("band2Vert" in style_regions)
    if v_bands and not look.get("noVBand", False):
        body_start = 1 if has_firstCol else 0
        body_end   = n_cols - 1 if has_lastCol else n_cols
        if body_start <= col_j < body_end:
            rel = col_j - body_start
            band_idx = (rel // max(1, col_band_size)) % 2
            regions.append("band1Vert" if band_idx == 0 else "band2Vert")

    if fc: regions.append("firstCol")
    if lc: regions.append("lastCol")
    if fr: regions.append("firstRow")
    if lr: regions.append("lastRow")
    if fr and lc: regions.append("neCell")
    if fr and fc: regions.append("nwCell")
    if lr and lc: regions.append("seCell")
    if lr and fc: regions.append("swCell")
    return regions


def effective_for_cell(resolved: dict, row_i: int, col_j: int,
                       n_rows: int, n_cols: int,
                       look: dict | None = None,
                       row_band_size: int = 1,
                       col_band_size: int = 1) -> tuple:
    """Compute (effective_pPr, effective_tcPr, effective_trPr) for given position."""
    pPr = copy.deepcopy(resolved["pPr"])
    tcPr = copy.deepcopy(resolved["tcPr"])
    trPr = copy.deepcopy(resolved["trPr"])
    style_regions = set(resolved["tblStylePr"].keys())
    regions = set(applicable_regions(
        row_i, col_j, n_rows, n_cols,
        style_regions=style_regions, look=look,
        row_band_size=row_band_size, col_band_size=col_band_size,
    ))
    for region in _REGION_ORDER:
        if region not in regions:
            continue
        block = resolved["tblStylePr"].get(region)
        if not block:
            continue
        pPr = merge_prop(pPr, block["pPr"])
        tcPr = merge_prop(tcPr, block["tcPr"])
        trPr = merge_prop(trPr, block["trPr"])
    return pPr, tcPr, trPr


# ---------- summary ----------
def summarize_table(tbl) -> dict:
    rows = tbl.findall(w("tr"))
    ncols = len(rows[0].findall(w("tc"))) if rows else 0
    tblPr = tbl.find(w("tblPr"))
    tblStyle = tblW = tblLook = None
    has_borders = False
    if tblPr is not None:
        ts = tblPr.find(w("tblStyle"))
        if ts is not None:
            tblStyle = ts.get(w("val"))
        tw = tblPr.find(w("tblW"))
        if tw is not None:
            tblW = f'{tw.get(w("w"))} {tw.get(w("type"))}'
        tl = tblPr.find(w("tblLook"))
        if tl is not None:
            flags = [k for k in ("firstRow", "lastRow", "firstColumn", "lastColumn")
                     if tl.get(w(k)) == "1"]
            tblLook = ",".join(flags) or "-"
        has_borders = tblPr.find(w("tblBorders")) is not None
    return {"rows": len(rows), "cols": ncols, "tblStyle": tblStyle,
            "tblW": tblW, "tblLook": tblLook, "has_tblBorders": has_borders}


def format_summary(idx: int, s: dict) -> str:
    parts = [
        f"[{idx}] {s['rows']}r x {s['cols']}c",
        f"style={s['tblStyle']!r}",
        f"width={s['tblW']}",
        f"tblLook={s['tblLook']}",
        f"borders={'Y' if s['has_tblBorders'] else 'N'}",
    ]
    return "  ".join(parts)


# ---------- applying to output table ----------
def replace_child_head(parent, tag: str, new_child) -> None:
    for e in list(parent.findall(tag)):
        parent.remove(e)
    if new_child is not None:
        parent.insert(0, new_child)


def rebuild_grid(sample_grid, out_cols: int):
    widths = []
    if sample_grid is not None:
        for gc in sample_grid.findall(w("gridCol")):
            try:
                widths.append(int(gc.get(w("w"), "0")))
            except ValueError:
                pass
    total = sum(widths) if widths else 9000
    each = max(1, total // max(1, out_cols))
    g = ET.Element(w("tblGrid"))
    for _ in range(out_cols):
        ET.SubElement(g, w("gridCol")).set(w("w"), str(each))
    return g


def apply_to_table(tbl, sample_tblPr, sample_tblGrid, resolved: dict,
                   override_jc: bool, center_tables: bool = False) -> dict:
    stats = {"rows": 0, "cells": 0}

    # 1. tblPr: clone sample's, but keep output's <w:tblStyle> link if present
    if sample_tblPr is not None:
        new_tblPr = copy.deepcopy(sample_tblPr)
        out_tblPr = tbl.find(w("tblPr"))
        if out_tblPr is not None:
            out_style = out_tblPr.find(w("tblStyle"))
            if out_style is not None:
                for s in list(new_tblPr.findall(w("tblStyle"))):
                    new_tblPr.remove(s)
                new_tblPr.insert(0, copy.deepcopy(out_style))
        if center_tables:
            for j in list(new_tblPr.findall(w("jc"))):
                new_tblPr.remove(j)
            jc = ET.Element(w("jc")); jc.set(w("val"), "center")
            new_tblPr.append(jc)
        replace_child_head(tbl, w("tblPr"), new_tblPr)
    elif center_tables:
        out_tblPr = tbl.find(w("tblPr"))
        if out_tblPr is None:
            out_tblPr = ET.Element(w("tblPr"))
            tbl.insert(0, out_tblPr)
        for j in list(out_tblPr.findall(w("jc"))):
            out_tblPr.remove(j)
        jc = ET.Element(w("jc")); jc.set(w("val"), "center")
        out_tblPr.append(jc)

    rows = tbl.findall(w("tr"))
    if not rows:
        return stats
    out_cols = len(rows[0].findall(w("tc")))

    # 2. tblGrid sized to output cols
    for g in list(tbl.findall(w("tblGrid"))):
        tbl.remove(g)
    new_grid = rebuild_grid(sample_tblGrid, out_cols)
    after_tblPr = tbl.find(w("tblPr"))
    insert_at = list(tbl).index(after_tblPr) + 1 if after_tblPr is not None else 0
    tbl.insert(insert_at, new_grid)

    # Effective tblLook + band sizes for conditional-region resolution.
    # Sample's tblLook overrides the style's (it's what lands on the output);
    # band sizes live on the style's tblPr (w:tblStyleRowBandSize/ColBandSize),
    # default 1.
    look = parse_tbl_look(sample_tblPr if sample_tblPr is not None
                          and sample_tblPr.find(w("tblLook")) is not None
                          else resolved.get("tblPr"))
    row_band = _int_child_val(resolved.get("tblPr"), "tblStyleRowBandSize", 1)
    col_band = _int_child_val(resolved.get("tblPr"), "tblStyleColBandSize", 1)

    n_rows = len(rows)
    for i, row in enumerate(rows):
        cells = row.findall(w("tc"))
        # Effective trPr (position-independent of col): use (i, 0)
        _, _, eff_trPr = effective_for_cell(
            resolved, i, 0, n_rows, out_cols,
            look=look, row_band_size=row_band, col_band_size=col_band)
        if eff_trPr is not None and list(eff_trPr):
            replace_child_head(row, w("trPr"), eff_trPr)

        for j, tc in enumerate(cells):
            eff_pPr, eff_tcPr, _ = effective_for_cell(
                resolved, i, j, n_rows, len(cells),
                look=look, row_band_size=row_band, col_band_size=col_band)

            if eff_tcPr is not None and list(eff_tcPr):
                # Preserve output's <w:tcW> (column width) if present
                out_tcPr = tc.find(w("tcPr"))
                if out_tcPr is not None:
                    out_tcW = out_tcPr.find(w("tcW"))
                    if out_tcW is not None and eff_tcPr.find(w("tcW")) is None:
                        eff_tcPr.append(copy.deepcopy(out_tcW))
                replace_child_head(tc, w("tcPr"), eff_tcPr)

            # Apply effective pPr to every paragraph in this cell
            for p in tc.findall(w("p")):
                saved_jc = None
                old_pPr = p.find(w("pPr"))
                if old_pPr is not None and not override_jc:
                    jc = old_pPr.find(w("jc"))
                    if jc is not None:
                        saved_jc = copy.deepcopy(jc)
                if eff_pPr is None or not list(eff_pPr):
                    continue
                new_pPr = copy.deepcopy(eff_pPr)
                # Preserve pStyle from the existing paragraph (so Pandoc's "Compact" stays)
                if old_pPr is not None:
                    pstyle = old_pPr.find(w("pStyle"))
                    if pstyle is not None and new_pPr.find(w("pStyle")) is None:
                        new_pPr.insert(0, copy.deepcopy(pstyle))
                # Markdown-explicit jc wins unless --override-jc
                if saved_jc is not None:
                    for oj in list(new_pPr.findall(w("jc"))):
                        new_pPr.remove(oj)
                    new_pPr.append(saved_jc)
                replace_child_head(p, w("pPr"), new_pPr)
            stats["cells"] += 1
        stats["rows"] += 1
    return stats


# ---------- programmatic API ----------
def _enum_templates(template_docx: str):
    tpl_root = ET.fromstring(read_zip_text(template_docx, "word/document.xml"))
    return tpl_root.findall(f".//{w('tbl')}")


def _resolved_for_sample(template_docx: str, sample_tbl) -> tuple:
    """Return (resolved_chain_dict, tbl_style_id, chain_list)."""
    sample_tblPr = sample_tbl.find(w("tblPr"))
    tbl_style_id = None
    if sample_tblPr is not None:
        ts = sample_tblPr.find(w("tblStyle"))
        if ts is not None:
            tbl_style_id = ts.get(w("val"))
    styles = parse_styles(template_docx)
    chain = []
    resolved = {"pPr": None, "tcPr": None, "trPr": None, "tblPr": None, "tblStylePr": {}}
    if tbl_style_id and tbl_style_id in styles:
        seen, cur = set(), tbl_style_id
        while cur and cur in styles and cur not in seen:
            seen.add(cur); chain.append(cur); cur = styles[cur]["basedOn"]
        resolved = resolve_chain(styles, tbl_style_id)
    return resolved, tbl_style_id, chain


def clone_tables(template_docx: str, target_docx: str,
                 out_docx: str | None = None,
                 sample_index: int | None = None,
                 override_jc: bool = False,
                 center_tables: bool = False,
                 verbose: bool = False,
                 print_prefix: str | None = None) -> dict:
    """Programmatic API. Clones sample table formatting onto every table in target.

    Returns dict:
      {cloned: bool, reason?: str, sample_index?: int, style_chain?: [..],
       regions?: [..], templates_tables?: int, tables_processed?: int,
       rows?: int, cells?: int, summaries?: [dict, ...]}
    print_prefix=None silences all output; otherwise lines are prefixed with it.
    """
    def pr(msg: str) -> None:
        if print_prefix is not None:
            print(f"{print_prefix}{msg}")

    tpl_tables = _enum_templates(template_docx)
    summaries = [summarize_table(t) for t in tpl_tables]
    if not tpl_tables:
        return {"cloned": False, "reason": "template-has-no-tables",
                "summaries": [], "templates_tables": 0}

    pr(f"template tables: {len(tpl_tables)}")
    for i, s in enumerate(summaries):
        pr(f"  {format_summary(i, s)}")

    idx = 0 if sample_index is None else sample_index
    if not (0 <= idx < len(tpl_tables)):
        return {"cloned": False, "reason": f"sample-index-out-of-range ({idx})",
                "summaries": summaries, "templates_tables": len(tpl_tables)}
    if sample_index is None and len(tpl_tables) > 1:
        pr(f"  (multiple samples — defaulting to index 0)")
    pr(f"  → using sample index {idx}")

    sample_tbl = tpl_tables[idx]
    sample_tblPr = sample_tbl.find(w("tblPr"))
    sample_tblGrid = sample_tbl.find(w("tblGrid"))
    resolved, style_id, chain = _resolved_for_sample(template_docx, sample_tbl)
    if style_id:
        pr(f"  style chain: {' -> '.join(chain)}")
        pr(f"  conditional regions: {sorted(resolved['tblStylePr'].keys()) or '(none)'}")
    else:
        pr(f"  no <w:tblStyle> — cloning direct formatting only")

    dst = out_docx or target_docx
    if dst != target_docx:
        shutil.copy2(target_docx, dst)

    out_root = ET.fromstring(read_zip_text(dst, "word/document.xml"))
    out_tables = out_root.findall(f".//{w('tbl')}")
    pr(f"target tables: {len(out_tables)}")
    if not out_tables:
        return {"cloned": False, "reason": "target-has-no-tables",
                "summaries": summaries, "templates_tables": len(tpl_tables),
                "sample_index": idx}

    totals = {"rows": 0, "cells": 0}
    for i, tbl in enumerate(out_tables, 1):
        s = apply_to_table(tbl, sample_tblPr, sample_tblGrid, resolved,
                           override_jc, center_tables=center_tables)
        totals["rows"] += s["rows"]; totals["cells"] += s["cells"]
        if verbose:
            pr(f"  Table {i}: rows={s['rows']} cells={s['cells']}")

    xml_text = ET.tostring(out_root, encoding="utf-8", xml_declaration=False).decode("utf-8")
    if not xml_text.lstrip().startswith("<?xml"):
        xml_text = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + xml_text
    rewrite_docx_part(dst, "word/document.xml", xml_text)

    pr(f"applied: {totals['rows']} rows, {totals['cells']} cells "
       f"(markdown alignment {'overridden' if override_jc else 'preserved'})")
    return {"cloned": True, "sample_index": idx,
            "style_chain": chain, "regions": sorted(resolved["tblStylePr"].keys()),
            "templates_tables": len(tpl_tables),
            "tables_processed": len(out_tables),
            "rows": totals["rows"], "cells": totals["cells"],
            "summaries": summaries}


# ---------- CLI ----------
def run(template_docx: str, target_docx: str, out_docx: str | None,
        sample_index: int | None, override_jc: bool, center_tables: bool,
        list_only: bool, verbose: bool) -> int:
    if list_only:
        tpl_tables = _enum_templates(template_docx)
        if not tpl_tables:
            print(f"ERROR: template '{template_docx}' has no tables.", file=sys.stderr)
            return 1
        print(f"Template tables found: {len(tpl_tables)}")
        for i, t in enumerate(tpl_tables):
            print(f"  {format_summary(i, summarize_table(t))}")
        return 0

    result = clone_tables(template_docx, target_docx, out_docx,
                          sample_index=sample_index,
                          override_jc=override_jc,
                          center_tables=center_tables,
                          verbose=verbose,
                          print_prefix="")
    if not result["cloned"]:
        print(f"ERROR: {result.get('reason')}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--template", required=True, help="Template .docx (must contain at least one table)")
    ap.add_argument("--target", required=True, help="Pandoc-produced .docx to format")
    ap.add_argument("--out", help="Output path (default: overwrite target)")
    ap.add_argument("--sample-index", type=int, default=None,
                    help="Which template table to sample (0-based). Default 0.")
    ap.add_argument("--list-only", action="store_true",
                    help="List template tables and exit.")
    ap.add_argument("--override-jc", action="store_true",
                    help="Override markdown's :---:/---: alignment with sample/style's jc")
    ap.add_argument("--center-tables", action="store_true",
                    help="Inject <w:jc w:val='center'/> into each output table's tblPr "
                         "(centers the table on the page, independent of cell text alignment).")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if not Path(args.template).exists():
        print(f"ERROR: template not found: {args.template}", file=sys.stderr); return 1
    if not args.list_only and not Path(args.target).exists():
        print(f"ERROR: target not found: {args.target}", file=sys.stderr); return 1
    return run(args.template, args.target, args.out,
               args.sample_index, args.override_jc, args.center_tables,
               args.list_only, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
