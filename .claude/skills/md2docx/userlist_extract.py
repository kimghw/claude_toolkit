#!/usr/bin/env python3
"""
md2docx/userlist_extract.py
  — reference docx 의 "표준 스타일" 단락 머릿글 관찰자.

설계 원칙
=========
이 스크립트는 단지 **관찰만 한다**. 마커 종류(①, (1), 가., -, □, ◌, …)
를 미리 정의하지 않는다. 표준(Normal/표준/본문) 스타일 + numPr 없음
단락의 머릿글·들여쓰기·폰트·문단 속성을 JSON·stdout 에 그대로 dump 한다.

어떤 머릿글이 사용자 정의 리스트 패턴인지 판단하는 일은 **Claude(LLM)
가 결과를 읽고 induction** 한다. Python 은 글리프 enum 을 하드코딩하지
않으므로 처음 보는 마커(□, ◌, ◇, ▶, ◦, … 또는 ASCII `-`/`*`)도 빠짐없이
드러난다.

LLM 는 observations 를 보고 같은 머릿글 + 같은 들여쓰기/폰트끼리 묶어
후보 cluster 를 만든 뒤 AskUserQuestion 으로 사용자에게 unordered /
ordered / 사용 안 함 셋 중 하나를 묻고, 답을 모아 직접
`template/userlist-<label>.json` (rules 파일) 을 작성한다.

Usage:
    python userlist_extract.py <reference.docx> --out <observations.json>

종료 코드:
    0 관찰 0건 (표준 스타일 본문 단락 없음)
    5 관찰 1건 이상 (LLM 패턴 도출 + 사용자 확인 필요)
"""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

NORMAL_STYLE_NAMES = {
    "Normal", "표준", "본문", "BodyText", "Body Text", "Default",
    "Paragraph", "para",
}


def _qn(tag):
    return f"{{{W_NS}}}{tag}"


def _para_text(p):
    return "".join(t.text or "" for t in p.iter(_qn("t")))


def _has_numpr(p):
    pPr = p.find(_qn("pPr"))
    return pPr is not None and pPr.find(_qn("numPr")) is not None


def _pstyle_val(p):
    pPr = p.find(_qn("pPr"))
    if pPr is None:
        return None
    ps = pPr.find(_qn("pStyle"))
    if ps is None:
        return None
    return ps.get(_qn("val"))


def _is_heading_style(style):
    if not style:
        return False
    low = style.lower()
    if "heading" in low or low.startswith("toc"):
        return True
    if style.startswith("제목"):
        return True
    return False


def _is_normal_style(style):
    """표준/Normal 계열 단락 스타일인지 (LLM 이 관찰할 대상)."""
    if style is None or style == "":
        return True
    if style in NORMAL_STYLE_NAMES:
        return True
    low = style.lower()
    if "normal" in low:
        return True
    if "본문" in style or "표준" in style:
        return True
    return False


def _ind_dict(pPr):
    if pPr is None:
        return None
    ind = pPr.find(_qn("ind"))
    if ind is None:
        return None
    return {
        "left": ind.get(_qn("left")),
        "hanging": ind.get(_qn("hanging")),
        "firstLine": ind.get(_qn("firstLine")),
        "right": ind.get(_qn("right")),
    }


def _spacing_dict(pPr):
    if pPr is None:
        return None
    sp = pPr.find(_qn("spacing"))
    if sp is None:
        return None
    return {
        "line": sp.get(_qn("line")),
        "lineRule": sp.get(_qn("lineRule")),
        "before": sp.get(_qn("before")),
        "after": sp.get(_qn("after")),
    }


def _jc_val(pPr):
    if pPr is None:
        return None
    jc = pPr.find(_qn("jc"))
    if jc is None:
        return None
    return jc.get(_qn("val"))


def _first_run_rpr(p):
    """첫 번째 <w:r> 의 <w:rPr> Element 반환 (없으면 None)."""
    for r in p.iter(_qn("r")):
        return r.find(_qn("rPr"))
    return None


def _rpr_summary(rPr):
    if rPr is None:
        return None
    rFonts = rPr.find(_qn("rFonts"))
    sz = rPr.find(_qn("sz"))
    color = rPr.find(_qn("color"))
    b = rPr.find(_qn("b"))
    i = rPr.find(_qn("i"))

    def _flag(elt):
        if elt is None:
            return False
        v = elt.get(_qn("val"))
        return v not in ("0", "false") if v is not None else True

    return {
        "rFonts_ascii": rFonts.get(_qn("ascii")) if rFonts is not None else None,
        "rFonts_hAnsi": rFonts.get(_qn("hAnsi")) if rFonts is not None else None,
        "rFonts_eastAsia": rFonts.get(_qn("eastAsia")) if rFonts is not None else None,
        "sz": sz.get(_qn("val")) if sz is not None else None,
        "color": color.get(_qn("val")) if color is not None else None,
        "b": _flag(b),
        "i": _flag(i),
    }


def _raw_xml(elt):
    if elt is None:
        return None
    ET.register_namespace("w", W_NS)
    return ET.tostring(elt, encoding="unicode")


def _load_styles_info(ref_docx):
    """word/styles.xml 파싱.

    반환:
      doc_default_pPr : Element or None  (docDefaults/pPrDefault/pPr)
      doc_default_rPr : Element or None  (docDefaults/rPrDefault/rPr)
      styles_by_id    : dict[styleId, {type, pPr, rPr, basedOn}]
      default_para_id : styleId of paragraph style with default='1' (보통 '표준'/'Normal')
    """
    try:
        with zipfile.ZipFile(ref_docx) as z:
            styles_xml = z.read("word/styles.xml").decode("utf-8")
    except (KeyError, zipfile.BadZipFile):
        return None, None, {}, None

    try:
        root = ET.fromstring(styles_xml)
    except ET.ParseError:
        return None, None, {}, None

    doc_default_pPr = None
    doc_default_rPr = None
    doc_defaults = root.find(_qn("docDefaults"))
    if doc_defaults is not None:
        pp_default = doc_defaults.find(_qn("pPrDefault"))
        if pp_default is not None:
            doc_default_pPr = pp_default.find(_qn("pPr"))
        rp_default = doc_defaults.find(_qn("rPrDefault"))
        if rp_default is not None:
            doc_default_rPr = rp_default.find(_qn("rPr"))

    styles_by_id = {}
    default_para_id = None
    for s in root.findall(_qn("style")):
        sid = s.get(_qn("styleId"))
        if sid is None:
            continue
        styp = s.get(_qn("type"))
        sdefault = s.get(_qn("default"))
        based_on = s.find(_qn("basedOn"))
        based_on_id = based_on.get(_qn("val")) if based_on is not None else None
        styles_by_id[sid] = {
            "type": styp,
            "pPr": s.find(_qn("pPr")),
            "rPr": s.find(_qn("rPr")),
            "basedOn": based_on_id,
        }
        if styp == "paragraph" and sdefault == "1" and default_para_id is None:
            default_para_id = sid

    return doc_default_pPr, doc_default_rPr, styles_by_id, default_para_id


def _merge_children(merged, source):
    """source 의 child element 를 merged 에 병합. 같은 tag 의 기존 child 는 source 가 덮어쓴다."""
    if source is None:
        return
    for child in source:
        existing = merged.find(child.tag)
        if existing is not None:
            merged.remove(existing)
        # deep copy via parse/serialize to detach from source tree
        merged.append(ET.fromstring(ET.tostring(child)))


def _resolve_cascade(p, doc_default_pPr, doc_default_rPr, styles_by_id, default_para_id):
    """단락 p 의 effective pPr/rPr 를 cascade 해소해 반환.

    순서: docDefaults → default 단락 스타일 (basedOn chain root→leaf) → pStyle 체인 → 단락 직접 값.
    각 단계의 child element 는 같은 tag 이면 후단계가 덮어쓴다.
    """
    eff_pPr = ET.Element(_qn("pPr"))
    eff_rPr = ET.Element(_qn("rPr"))

    _merge_children(eff_pPr, doc_default_pPr)
    _merge_children(eff_rPr, doc_default_rPr)

    direct_pPr = p.find(_qn("pPr"))
    pstyle_val = None
    if direct_pPr is not None:
        ps = direct_pPr.find(_qn("pStyle"))
        if ps is not None:
            pstyle_val = ps.get(_qn("val"))

    target_sid = pstyle_val if pstyle_val else default_para_id

    chain = []
    sid = target_sid
    visited = set()
    while sid and sid in styles_by_id and sid not in visited:
        visited.add(sid)
        chain.append(sid)
        sid = styles_by_id[sid].get("basedOn")

    for sid in reversed(chain):
        info = styles_by_id[sid]
        _merge_children(eff_pPr, info.get("pPr"))
        _merge_children(eff_rPr, info.get("rPr"))

    _merge_children(eff_pPr, direct_pPr)
    direct_rPr = _first_run_rpr(p)
    _merge_children(eff_rPr, direct_rPr)

    return eff_pPr, eff_rPr


def _short(s, n):
    s = (s or "").replace("\n", " ").replace("\r", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _label(stem):
    for prefix in ("reference_", "reference-"):
        if stem.lower().startswith(prefix):
            return stem[len(prefix):]
    return stem


def _fmt_sz(sz):
    if not sz:
        return "?pt"
    try:
        return f"{int(sz) / 2:g}pt"
    except ValueError:
        return f"{sz}?pt"


def _leading_token(text):
    """단락의 첫 whitespace 이전 토큰. 비었거나 첫 글자가 공백이면 첫 1자."""
    if not text:
        return ""
    parts = text.split(None, 1)
    if not parts:
        return text[:1]
    return parts[0]


def _normalize_head_for_cluster(text):
    """cluster key 용 머릿글 정규화.

    숫자 연쇄 → 'N', 라틴 연쇄 → 'A', 한글 음절 연쇄 → 'H' 로 치환해
    `1.`/`12.`/`23.` 또는 `(1)`/`(12)` 같은 ordered 시퀀스가 한 cluster 로 묶이도록.
    enclosed alphanumeric(①②③ 등) 은 regex 에 안 잡혀 별도 cluster 로 남는다 — LLM 이
    dump 보고 사후 묶음.
    """
    leading = _leading_token(text)
    leading = re.sub(r"\d+", "N", leading)
    leading = re.sub(r"[A-Za-z]+", "A", leading)
    leading = re.sub(r"[가-힣]+", "H", leading)
    return leading[:8]  # 비정상적으로 긴 leading 안전 cap


def observe(ref_docx):
    """표준 스타일 + numPr 없음 단락 cluster dump.

    같은 (정규화 머릿글 + 들여쓰기 + 폰트 + pStyle + sz) cluster 는 첫 observation
    만 유지하고 `sample_count` / `sample_indices` 로 압축한다. 마커 판정·prose 제외
    같은 후속 판단은 LLM 이 cluster dump 를 보고 수행.
    """
    with zipfile.ZipFile(ref_docx) as z:
        doc_xml = z.read("word/document.xml").decode("utf-8")
    root = ET.fromstring(doc_xml)
    body = root.find(_qn("body"))
    if body is None:
        return []

    # styles.xml 의 docDefaults + default 단락 스타일 + 전체 style 인덱스 로드.
    # 단락의 효과적인 pPr/rPr 은 cascade (docDefaults → default style chain → 직접) 해소가 필요.
    doc_default_pPr, doc_default_rPr, styles_by_id, default_para_id = _load_styles_info(ref_docx)

    paragraphs = list(body.iter(_qn("p")))
    clusters = {}  # cluster key → first observation dict (with sample_count, sample_indices)

    for idx, p in enumerate(paragraphs):
        if _has_numpr(p):
            continue
        style = _pstyle_val(p)
        if _is_heading_style(style):
            continue
        if not _is_normal_style(style):
            continue
        text = _para_text(p)
        if not text or not text.strip():
            continue

        pPr = p.find(_qn("pPr"))
        rPr = _first_run_rpr(p)

        # cascade-해소된 effective pPr/rPr (docDefaults + default style + 직접 병합).
        eff_pPr, eff_rPr = _resolve_cascade(
            p, doc_default_pPr, doc_default_rPr, styles_by_id, default_para_id
        )

        stripped = text.lstrip("﻿").lstrip()
        head_chars = stripped[:8]
        head_token = _leading_token(stripped)[:8]
        ind = _ind_dict(pPr) or _ind_dict(eff_pPr)
        eff_spacing = _spacing_dict(eff_pPr)
        eff_jc = _jc_val(eff_pPr)
        eff_rpr_sum = _rpr_summary(eff_rPr)

        # cluster key — 머릿글 정규화 + 들여쓰기 + 폰트 + pStyle + 크기.
        # 같은 cluster 의 다른 인스턴스는 sample_count 만 증가시킨다.
        key = (
            _normalize_head_for_cluster(stripped),
            (ind or {}).get("left"),
            (ind or {}).get("hanging"),
            (ind or {}).get("firstLine"),
            (eff_rpr_sum or {}).get("rFonts_ascii"),
            (eff_rpr_sum or {}).get("rFonts_eastAsia"),
            (eff_rpr_sum or {}).get("sz"),
            style,
        )

        existing = clusters.get(key)
        if existing is not None:
            existing["sample_count"] += 1
            if len(existing["sample_indices"]) < 6:
                existing["sample_indices"].append(idx)
            return_text = _short(stripped, 120)
            if return_text != existing["text"] and len(existing["alt_samples"]) < 3:
                existing["alt_samples"].append(return_text)
            continue

        clusters[key] = {
            "idx": idx,
            "pStyle": style,
            "head_token": head_token,
            "head_chars": head_chars,
            "head_normalized": _normalize_head_for_cluster(stripped),
            "text": _short(stripped, 120),
            "alt_samples": [],
            "sample_count": 1,
            "sample_indices": [idx],
            "indent": ind,
            # spacing/jc/rPr 은 effective (cascade 해소된 값) — 단락이 표준 스타일/docDefaults
            # 에서 상속받는 spacing·line·jc·font 등이 포함된다.
            "spacing": eff_spacing,
            "jc": eff_jc,
            "rPr": eff_rpr_sum,
            # 직접 값(원본 단락에 명시된 것) — 디버깅/감리용으로 별도 보관.
            "pPr_xml_direct": _raw_xml(pPr),
            "rPr_xml_direct": _raw_xml(rPr),
            # effective XML — catalog 작성 시 이 값을 사용 (단락의 완전한 문단 정보 포함).
            "pPr_xml": _raw_xml(eff_pPr),
            "rPr_xml": _raw_xml(eff_rPr),
        }

    # 첫 등장 idx 기준 정렬 (문서 순서 보존)
    return sorted(clusters.values(), key=lambda c: c["idx"])


def main():
    ap = argparse.ArgumentParser(
        description="reference docx 의 표준 스타일 단락 머릿글 관찰 "
                    "(마커 판정은 LLM 이 사후 수행)"
    )
    ap.add_argument("reference", help="대상 reference docx")
    ap.add_argument("--out", required=True, metavar="JSON",
                    help="관찰 결과 저장 경로 (observations 배열 포함)")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ref = Path(args.reference)
    out = Path(args.out)
    if not ref.exists():
        print(f"ERROR: reference not found: {ref}", file=sys.stderr)
        return 1

    try:
        obs = observe(ref)
    except zipfile.BadZipFile as e:
        print(f"ERROR: bad docx (zip): {e}", file=sys.stderr)
        return 1
    except ET.ParseError as e:
        print(f"ERROR: bad docx (xml): {e}", file=sys.stderr)
        return 1
    except KeyError as e:
        print(f"ERROR: word/document.xml 없음: {e}", file=sys.stderr)
        return 1

    label = _label(ref.stem)
    payload = {
        "reference": ref.name,
        "label": label,
        "observations": obs,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    for o in obs:
        ind = o["indent"] or {}
        rpr = o["rPr"] or {}
        sp = o["spacing"] or {}
        font = rpr.get("rFonts_ascii") or rpr.get("rFonts_eastAsia") or "-"
        sz = _fmt_sz(rpr.get("sz"))
        left = ind.get("left")
        hanging = ind.get("hanging")
        first_line = ind.get("firstLine")
        line = sp.get("line")
        before = sp.get("before")
        after = sp.get("after")
        jc = o["jc"] or "-"
        ps = o["pStyle"] if o["pStyle"] else "(None=표준)"
        alt = f" | alt={o['alt_samples']}" if o["alt_samples"] else ""
        print(
            f"[USERLIST-OBS] cluster='{o['head_normalized']}' | count={o['sample_count']} | "
            f"first_idx={o['idx']} | indices={o['sample_indices']} | "
            f"ind=left={left},hanging={hanging},firstLine={first_line} | "
            f"spacing=line={line},before={before},after={after} | jc={jc} | "
            f"font='{font}' {sz} | "
            f"pStyle='{ps}' | text='{o['text']}'{alt}"
        )
    total_samples = sum(o["sample_count"] for o in obs)
    print(f"[USERLIST-OBS-COUNT] clusters={len(obs)} samples={total_samples}")
    print(f"[USERLIST-OUT] {out.resolve()}")
    return 5 if obs else 0


if __name__ == "__main__":
    sys.exit(main())
