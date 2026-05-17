#!/usr/bin/env python3
"""
md2docx/postprocess_userlist.py
  — pandoc 가 생성한 진짜 list 단락(<w:numPr> 보유)을 회사 reference 에서 추출한
    pseudo-list cluster 패턴(□ / ◌ / - / ① / (1) / 가. 등 + 들여쓰기·폰트)으로 변환.

입력 두 갈래로 분리:
    --catalog <userlist-<label>.json>   reference 의 cluster 정의 (per-reference)
    --mapping <userlist-mapping.json>   pandoc list_kind → cluster_id 결정 (per-conversion)

list_kind 단위 = (numFmt, ilvl). 예: (bullet, "0"), (bullet, "1"), (decimal, "0").
mapping 의 list_rules 가 각 list_kind 에 어떤 cluster 를 적용할지 명시한다.
cluster_id 가 null 이면 그 list_kind 는 변환하지 않고 그대로 둔다.

알고리즘:
    1) numbering.xml 의 numId → numFmt(ilvl=0) 구축
    2) document.xml 의 numPr 단락마다 (numFmt, ilvl) 추정 → mapping 에서 cluster_id 조회
    3) catalog 에서 cluster_id → cluster 정의 (pPr_xml/rPr_xml/marker_sequence)
    4) 단락에서 numPr 제거, ind/spacing/jc 교체, marker run prepend, 기존 run rFonts/sz merge

Usage:
    python postprocess_userlist.py <docx> --catalog <catalog.json> --mapping <mapping.json>
"""

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path


# ---------- .env 로더 (stdlib only) ----------

def load_env(env_path: Path) -> dict:
    """skill 루트의 .env 파일을 dict 로 로드. 없으면 {} 반환.

    형식: KEY=VALUE, '#' 주석 무시, 빈 줄 무시. 값은 양쪽 따옴표 제거.
    """
    out = {}
    if not env_path.exists():
        return out
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, _, v = s.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ('"', "'"):
            v = v[1:-1]
        out[k.strip()] = v
    return out


def _truthy(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


# ---------- numbering.xml 분석 ----------

def build_numid_kind_map(numbering_xml):
    """numId → ("unordered"|"ordered", numFmt_raw) 매핑.

    numbering.xml 이 없거나 파싱 실패하면 {} 반환.
    """
    if not numbering_xml:
        return {}

    # abstractNumId → ilvl=0 의 numFmt
    abs_fmt = {}
    for m in re.finditer(
        r'<w:abstractNum\s+[^>]*w:abstractNumId="(\d+)"[^>]*>(.*?)</w:abstractNum>',
        numbering_xml,
        re.DOTALL,
    ):
        abs_id = m.group(1)
        body = m.group(2)
        lvl_m = re.search(
            r'<w:lvl\s+[^>]*w:ilvl="0"[^>]*>(.*?)</w:lvl>', body, re.DOTALL
        )
        if not lvl_m:
            continue
        fmt_m = re.search(r'<w:numFmt\s+[^>]*w:val="([^"]+)"', lvl_m.group(1))
        if fmt_m:
            abs_fmt[abs_id] = fmt_m.group(1)

    # numId → abstractNumId
    out = {}
    for m in re.finditer(
        r'<w:num\s+[^>]*w:numId="(\d+)"[^>]*>(.*?)</w:num>',
        numbering_xml,
        re.DOTALL,
    ):
        num_id = m.group(1)
        body = m.group(2)
        ref_m = re.search(r'<w:abstractNumId\s+[^>]*w:val="(\d+)"', body)
        if not ref_m:
            continue
        abs_id = ref_m.group(1)
        fmt = abs_fmt.get(abs_id)
        if not fmt:
            continue
        kind = "unordered" if fmt == "bullet" else "ordered"
        out[num_id] = (kind, fmt)
    return out


# ---------- rule 해석 ----------

def _extract_tag(xml, tag):
    """문자열 xml 안에서 첫 <w:tag .../> 또는 <w:tag ...>...</w:tag> 를 반환. 없으면 None."""
    if not xml:
        return None
    m = re.search(rf'<w:{tag}\b[^/>]*/>', xml)
    if m:
        return m.group(0)
    m = re.search(rf'<w:{tag}\b[^>]*>.*?</w:{tag}>', xml, re.DOTALL)
    if m:
        return m.group(0)
    return None


def _build_ind_from_struct(ind):
    if not ind:
        return None
    attrs = []
    for k_json, k_xml in (("left", "left"), ("hanging", "hanging"), ("firstLine", "firstLine")):
        v = ind.get(k_json)
        if v is not None and v != "":
            attrs.append(f'w:{k_xml}="{v}"')
    if not attrs:
        return None
    return f'<w:ind {" ".join(attrs)}/>'


def _build_spacing_from_struct(sp):
    if not sp:
        return None
    attrs = []
    for k_json, k_xml in (("line", "line"), ("lineRule", "lineRule"), ("before", "before"), ("after", "after")):
        v = sp.get(k_json)
        if v is not None and v != "":
            attrs.append(f'w:{k_xml}="{v}"')
    if not attrs:
        return None
    return f'<w:spacing {" ".join(attrs)}/>'


def _build_jc_from_struct(jc):
    if not jc:
        return None
    return f'<w:jc w:val="{jc}"/>'


def _build_rpr_from_struct(rpr):
    """structured rPr dict 에서 <w:rPr>...</w:rPr> XML 구성."""
    if not rpr:
        return None
    parts = []
    rfonts_attrs = []
    for k_json, k_xml in (
        ("rFonts_ascii", "ascii"),
        ("rFonts_hAnsi", "hAnsi"),
        ("rFonts_eastAsia", "eastAsia"),
        ("rFonts_cs", "cs"),
    ):
        v = rpr.get(k_json)
        if v:
            rfonts_attrs.append(f'w:{k_xml}="{v}"')
    if rfonts_attrs:
        parts.append(f'<w:rFonts {" ".join(rfonts_attrs)}/>')
    if rpr.get("b"):
        parts.append("<w:b/>")
    if rpr.get("i"):
        parts.append("<w:i/>")
    color = rpr.get("color")
    if color:
        parts.append(f'<w:color w:val="{color}"/>')
    sz = rpr.get("sz")
    if sz:
        parts.append(f'<w:sz w:val="{sz}"/>')
        parts.append(f'<w:szCs w:val="{sz}"/>')
    if not parts:
        return None
    return f'<w:rPr>{"".join(parts)}</w:rPr>'


def resolve_rule(rule):
    """rule dict → 적용에 필요한 정규화된 조각.

    Returns dict:
        ind_xml:     <w:ind .../> or None
        spacing_xml: <w:spacing .../> or None
        jc_xml:      <w:jc .../> or None
        rpr_xml:     <w:rPr>...</w:rPr> or None  (marker run 및 기존 run merge 용)
        markers:     list[str]
        rule_id:     문자열
    """
    pPr_xml = rule.get("pPr_xml") or ""
    rPr_xml = rule.get("rPr_xml") or ""

    ind_xml = _extract_tag(pPr_xml, "ind") or _build_ind_from_struct(rule.get("indent"))
    spacing_xml = _extract_tag(pPr_xml, "spacing") or _build_spacing_from_struct(rule.get("spacing"))
    jc_xml = _extract_tag(pPr_xml, "jc") or _build_jc_from_struct(rule.get("jc"))

    if rPr_xml.strip():
        rpr_xml = rPr_xml
    else:
        rpr_xml = _build_rpr_from_struct(rule.get("rPr"))

    markers = rule.get("marker_sequence") or []
    if not markers:
        fom = rule.get("first_observed_marker")
        if fom:
            markers = [fom]

    return {
        "ind_xml": ind_xml,
        "spacing_xml": spacing_xml,
        "jc_xml": jc_xml,
        "rpr_xml": rpr_xml,
        "markers": markers,
        "rule_id": rule.get("id") or rule.get("marker_kind") or "?",
    }


# ---------- 단락 변형 ----------

NUMPR_RE = re.compile(r"<w:numPr\b[^>]*>.*?</w:numPr>", re.DOTALL)
NUMPR_SELF_RE = re.compile(r"<w:numPr\b[^/>]*/>", re.DOTALL)
PPR_RE = re.compile(r"<w:pPr>(.*?)</w:pPr>", re.DOTALL)
P_RE = re.compile(r"<w:p\b[^>]*>(.*?)</w:p>", re.DOTALL)


def _read_numpr(ppr_inner):
    """pPr 내부의 <w:numPr>...</w:numPr> 본문에서 (numId, ilvl) 추출. 없으면 (None,None)."""
    m = NUMPR_RE.search(ppr_inner)
    if not m:
        m2 = NUMPR_SELF_RE.search(ppr_inner)
        if not m2:
            return None, None
        body = ""
    else:
        body = m.group(0)
    nid_m = re.search(r'<w:numId\s+[^>]*w:val="(\d+)"', body)
    ilvl_m = re.search(r'<w:ilvl\s+[^>]*w:val="(\d+)"', body)
    nid = nid_m.group(1) if nid_m else None
    ilvl = ilvl_m.group(1) if ilvl_m else "0"
    return nid, ilvl


def _strip_tag(xml, tag):
    """xml 안에서 <w:tag .../> 와 <w:tag ...>...</w:tag> 를 모두 제거."""
    xml = re.sub(rf'<w:{tag}\b[^/>]*/>', "", xml)
    xml = re.sub(rf'<w:{tag}\b[^>]*>.*?</w:{tag}>', "", xml, flags=re.DOTALL)
    return xml


def _merge_run_rpr(run_xml, rule_rpr_xml):
    """기존 run 의 rPr 에 rule 의 rFonts/sz/szCs 만 덮어쓴다. bold/italic/color 등은 유지.

    run 내부에 <w:tab/> / <w:br/> 만 있으면 변경하지 않는다.
    """
    if not rule_rpr_xml:
        return run_xml

    # tab/br 전용 run 은 skip
    inner_m = re.match(r"<w:r\b[^>]*>(.*?)</w:r>", run_xml, re.DOTALL)
    if not inner_m:
        return run_xml
    body = inner_m.group(1)
    body_no_rpr = re.sub(r"<w:rPr>.*?</w:rPr>", "", body, flags=re.DOTALL)
    if body_no_rpr.strip() and re.fullmatch(r"(\s*<w:(tab|br)\b[^/>]*/>\s*)+", body_no_rpr):
        return run_xml

    # rule rpr 에서 필요한 조각만 뽑기
    rfonts_m = re.search(r"<w:rFonts\b[^/>]*/>", rule_rpr_xml)
    sz_m = re.search(r"<w:sz\b[^/>]*/>", rule_rpr_xml)
    szcs_m = re.search(r"<w:szCs\b[^/>]*/>", rule_rpr_xml)

    rpr_existing_m = re.search(r"<w:rPr>(.*?)</w:rPr>", body, re.DOTALL)
    if rpr_existing_m:
        rpr_inner = rpr_existing_m.group(1)
        for tag in ("rFonts", "sz", "szCs"):
            rpr_inner = re.sub(rf'<w:{tag}\b[^/>]*/>', "", rpr_inner)
        injection = ""
        if rfonts_m:
            injection += rfonts_m.group(0)
        if sz_m:
            injection += sz_m.group(0)
        if szcs_m:
            injection += szcs_m.group(0)
        new_rpr = f"<w:rPr>{injection}{rpr_inner}</w:rPr>"
        new_body = body[: rpr_existing_m.start()] + new_rpr + body[rpr_existing_m.end():]
    else:
        injection = ""
        if rfonts_m:
            injection += rfonts_m.group(0)
        if sz_m:
            injection += sz_m.group(0)
        if szcs_m:
            injection += szcs_m.group(0)
        if not injection:
            return run_xml
        new_rpr = f"<w:rPr>{injection}</w:rPr>"
        # <w:r ...> 직후에 rPr 를 넣는다
        new_body = new_rpr + body

    head_m = re.match(r"<w:r\b[^>]*>", run_xml)
    return f"{head_m.group(0)}{new_body}</w:r>"


def _patch_ppr_for_userlist(ppr_inner, resolved):
    """단락 pPr 내부에서 numPr 제거 + ind/spacing/jc 교체.

    각 속성은 resolved 에 값이 있을 때만 기존 제거 + 새로 삽입한다.
    None 이면 (env 토글로 비활성됐거나 cluster 정의 누락) 단락의 기존 값을 그대로 둔다.
    """
    # numPr 제거 (필수 — 항상)
    new = NUMPR_RE.sub("", ppr_inner)
    new = NUMPR_SELF_RE.sub("", new)

    insertion = ""
    for tag, xml in (("ind", resolved.get("ind_xml")),
                     ("spacing", resolved.get("spacing_xml")),
                     ("jc", resolved.get("jc_xml"))):
        if xml:
            new = _strip_tag(new, tag)
            insertion += xml
    return new + insertion


def _transform_paragraph(p_xml, resolved, marker_text):
    """한 단락 XML 전체를 변환. (numPr 제거 → ind/spacing/jc 교체 → marker run prepend → 기존 run rPr merge)"""
    # 1) pPr 패치
    ppr_m = PPR_RE.search(p_xml)
    if ppr_m:
        new_ppr_inner = _patch_ppr_for_userlist(ppr_m.group(1), resolved)
        new_p = p_xml[: ppr_m.start()] + f"<w:pPr>{new_ppr_inner}</w:pPr>" + p_xml[ppr_m.end():]
    else:
        # pPr 없는 numPr 단락은 사실상 없겠지만, 안전망으로 빈 pPr 삽입
        opening_m = re.match(r"<w:p\b[^>]*>", p_xml)
        new_p = opening_m.group(0) + "<w:pPr></w:pPr>" + p_xml[opening_m.end():]

    # 2) marker run 생성
    marker_rpr = resolved["rpr_xml"] or ""
    marker_run = (
        f'<w:r>{marker_rpr}'
        f'<w:t xml:space="preserve">{marker_text} </w:t>'
        f'</w:r>'
    )

    # 3) 기존 run 들의 rPr merge + 첫 run 앞에 marker_run 삽입
    # </w:pPr> 직후가 단락 본문 시작 지점이다.
    close_idx = new_p.find("</w:pPr>")
    if close_idx == -1:
        opening_m = re.match(r"<w:p\b[^>]*>", new_p)
        head_end = opening_m.end()
        head = new_p[:head_end]
        body = new_p[head_end:]
    else:
        head_end = close_idx + len("</w:pPr>")
        head = new_p[:head_end]
        body = new_p[head_end:]

    # body 안에서 <w:r ...>...</w:r> 들을 찾아 rPr merge
    def repl_run(m):
        return _merge_run_rpr(m.group(0), resolved["rpr_xml"])

    new_body = re.sub(r"<w:r\b[^>]*>.*?</w:r>", repl_run, body, flags=re.DOTALL)

    # marker_run 을 첫 번째 <w:r> 바로 앞에 삽입.
    # 첫 run 이 없으면(=빈 단락) body 맨 앞에 그냥 둔다.
    first_run_m = re.search(r"<w:r\b[^>]*>", new_body)
    if first_run_m:
        idx = first_run_m.start()
        new_body = new_body[:idx] + marker_run + new_body[idx:]
    else:
        new_body = marker_run + new_body

    return head + new_body


# ---------- document.xml 전체 처리 ----------

def patch_document_xml(doc_xml, list_rules, numid_to_fmt):
    """문서 전체를 순회하며 매칭되는 list 단락을 변환.

    list_rules: [{"match": {"numFmt", "ilvl"}, "cluster_id", "cluster_def"}, ...]
                cluster_def 는 resolve_rule() 결과 (None 이면 skip).

    Returns:
        (new_doc_xml, stats_dict)
        stats_dict = {
            "by_kind": {(numFmt, ilvl): {"count": int, "cluster_id": str|None, "matched": bool}},
            "total_modified": int,
        }
    """
    # (numFmt, ilvl) → (cluster_id, resolved cluster_def or None)
    kind_to_rule = {}
    for r in list_rules:
        match = r.get("match") or {}
        num_fmt = match.get("numFmt")
        ilvl = match.get("ilvl")
        if num_fmt is None or ilvl is None:
            continue
        kind_to_rule[(num_fmt, str(ilvl))] = (r.get("cluster_id"), r.get("cluster_def"))

    paragraphs = []
    for m in P_RE.finditer(doc_xml):
        paragraphs.append((m.start(), m.end(), m.group(0)))

    # 각 단락 (numId, ilvl, numFmt) 식별
    para_info = []
    for start, end, p_xml in paragraphs:
        ppr_m = PPR_RE.search(p_xml)
        if not ppr_m or "<w:numPr" not in ppr_m.group(1):
            para_info.append({"start": start, "end": end, "p_xml": p_xml,
                              "numId": None, "ilvl": None, "numFmt": None})
            continue
        nid, ilvl = _read_numpr(ppr_m.group(1))
        fmt_info = numid_to_fmt.get(nid) if nid else None
        num_fmt = fmt_info[1] if fmt_info else "unknown"
        para_info.append({
            "start": start, "end": end, "p_xml": p_xml,
            "numId": nid, "ilvl": ilvl, "numFmt": num_fmt,
        })

    stats = {"by_kind": {}, "total_modified": 0}
    # 같은 numId 연속 run 별 marker 카운터
    prev_numid = None
    run_pos = 0
    replacements = []

    for info in para_info:
        nid = info["numId"]
        ilvl = info["ilvl"]
        num_fmt = info["numFmt"]

        if nid is None and ilvl is None:
            prev_numid = None
            continue

        kind_key = (num_fmt, ilvl)
        bucket = stats["by_kind"].setdefault(kind_key, {
            "count": 0, "cluster_id": None, "matched": False,
            "in_mapping": False, "explicit_skip": False,
        })

        rule_entry = kind_to_rule.get(kind_key)
        if rule_entry is None:
            # mapping 에 없는 list_kind — 그대로 둠 (다른 후처리가 처리)
            prev_numid = nid
            continue

        bucket["in_mapping"] = True
        cluster_id, cluster_def = rule_entry
        bucket["cluster_id"] = cluster_id

        if cluster_id is None:
            # mapping 에 list_rule 은 있지만 cluster_id=null → 명시적 사용 안 함
            bucket["explicit_skip"] = True
            bucket["matched"] = False
            prev_numid = nid
            continue
        if cluster_def is None:
            # cluster_id 가 catalog 에 없거나 marker_sequence 비어있음
            bucket["matched"] = False
            prev_numid = nid
            continue

        if nid != prev_numid:
            run_pos = 0
        prev_numid = nid

        markers = cluster_def["markers"]
        if not markers:
            bucket["matched"] = False
            continue
        marker = markers[run_pos % len(markers)]
        new_p_xml = _transform_paragraph(info["p_xml"], cluster_def, marker)
        replacements.append((info["start"], info["end"], new_p_xml))

        bucket["matched"] = True
        bucket["count"] += 1
        stats["total_modified"] += 1
        run_pos += 1

    if not replacements:
        return doc_xml, stats

    replacements.sort(key=lambda x: x[0])
    out = []
    cursor = 0
    for start, end, new_xml in replacements:
        out.append(doc_xml[cursor:start])
        out.append(new_xml)
        cursor = end
    out.append(doc_xml[cursor:])
    return "".join(out), stats


# ---------- 진입 ----------

def load_catalog_and_mapping(catalog_path, mapping_path):
    """catalog (cluster 정의) + mapping (list_kind → cluster_id) 를 읽어
    각 list_rule 의 cluster_def 를 inline 한 list_rules[] 반환.
    """
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    with open(mapping_path, "r", encoding="utf-8") as f:
        mapping = json.load(f)

    clusters = catalog.get("clusters") or []
    by_id = {c.get("id"): c for c in clusters if c.get("id")}

    list_rules = []
    for r in (mapping.get("list_rules") or []):
        cluster_id = r.get("cluster_id")
        cluster_def = None
        if cluster_id:
            cluster = by_id.get(cluster_id)
            if cluster is None:
                print(
                    f"[POSTPROCESS-USERLIST-WARN] cluster_id='{cluster_id}' 가 catalog 에 없음 — skip",
                    file=sys.stderr,
                )
            else:
                cluster_def = resolve_rule(cluster)
        list_rules.append({
            "match": r.get("match") or {},
            "cluster_id": cluster_id,
            "cluster_def": cluster_def,
        })
    return list_rules


def process(docx_path, catalog_path, mapping_path):
    list_rules = load_catalog_and_mapping(catalog_path, mapping_path)
    if not list_rules:
        print("[POSTPROCESS-USERLIST] mapping 의 list_rules 0개 — skip")
        return 0

    # .env 토글 로드 — skill 루트 기준 (이 스크립트와 같은 폴더).
    env = load_env(Path(__file__).resolve().parent / ".env")
    apply_rpr = _truthy(env.get("USERLIST_APPLY_RPR", "true"))
    apply_ind = _truthy(env.get("USERLIST_APPLY_INDENT", "true"))
    apply_spacing = _truthy(env.get("USERLIST_APPLY_SPACING", "true"))
    apply_jc = _truthy(env.get("USERLIST_APPLY_JC", "true"))

    toggles_off = []
    for name, on in (("RPR", apply_rpr), ("INDENT", apply_ind),
                     ("SPACING", apply_spacing), ("JC", apply_jc)):
        if not on:
            toggles_off.append(name)
    if toggles_off:
        print(f"[POSTPROCESS-USERLIST] .env 토글 비활성: {', '.join(toggles_off)} (해당 속성은 cluster 값 무시, 단락 기존 값 유지)")

    # 토글에 따라 resolved cluster_def 의 해당 속성을 None 으로 변경.
    for r in list_rules:
        cd = r.get("cluster_def")
        if cd is None:
            continue
        if not apply_rpr:
            cd["rpr_xml"] = None
        if not apply_ind:
            cd["ind_xml"] = None
        if not apply_spacing:
            cd["spacing_xml"] = None
        if not apply_jc:
            cd["jc_xml"] = None

    summary = []
    for r in list_rules:
        match = r.get("match") or {}
        summary.append(
            f"({match.get('numFmt')},ilvl={match.get('ilvl')})→{r.get('cluster_id') or 'skip'}"
        )
    print(f"[POSTPROCESS-USERLIST] list_rules {len(list_rules)}개 로드: {', '.join(summary)}")

    tmp = docx_path.with_suffix(docx_path.suffix + ".tmp")
    stats = {"by_kind": {}, "total_modified": 0}
    with zipfile.ZipFile(docx_path, "r") as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        numbering_xml = ""
        try:
            numbering_xml = zin.read("word/numbering.xml").decode("utf-8")
        except KeyError:
            numbering_xml = ""
        numid_to_fmt = build_numid_kind_map(numbering_xml)

        for item in zin.namelist():
            data = zin.read(item)
            if item == "word/document.xml":
                doc_xml = data.decode("utf-8")
                new_doc, stats = patch_document_xml(doc_xml, list_rules, numid_to_fmt)
                data = new_doc.encode("utf-8")
            zout.writestr(item, data)

    shutil.move(str(tmp), str(docx_path))

    for kind_key, info in sorted(stats["by_kind"].items()):
        num_fmt, ilvl = kind_key
        cid = info.get("cluster_id")
        if info.get("matched"):
            print(
                f"[POSTPROCESS-USERLIST] 처리: numFmt={num_fmt} ilvl={ilvl} "
                f"→ cluster '{cid}' 적용, {info['count']}개 단락"
            )
        elif info.get("explicit_skip"):
            print(
                f"[POSTPROCESS-USERLIST] 명시적 skip: numFmt={num_fmt} ilvl={ilvl} "
                f"(mapping 의 cluster_id=null — pandoc 기본 유지)"
            )
        elif not info.get("in_mapping"):
            print(
                f"[POSTPROCESS-USERLIST] 미매핑: numFmt={num_fmt} ilvl={ilvl} "
                f"(mapping 의 list_rules 에 해당 list_kind 없음 — 그대로 유지)"
            )
        else:
            print(
                f"[POSTPROCESS-USERLIST] 정의 누락: numFmt={num_fmt} ilvl={ilvl} "
                f"→ cluster_id='{cid}' 가 catalog 에 없거나 marker_sequence 비어있음"
            )

    print(f"[POSTPROCESS-USERLIST-OK] 총 {stats['total_modified']}개 단락에 사용자 정의 리스트 적용")
    return stats["total_modified"]


def main():
    ap = argparse.ArgumentParser(
        description="pandoc list 단락을 reference 의 pseudo-list cluster 로 변환"
    )
    ap.add_argument("docx", help="post-processing 대상 docx (in-place 수정)")
    ap.add_argument("--catalog", required=True, metavar="JSON",
                    help="per-reference cluster catalog (template/userlist-<label>.json)")
    ap.add_argument("--mapping", required=True, metavar="JSON",
                    help="per-conversion list_kind → cluster_id 매핑 (userlist-mapping.json)")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    docx = Path(args.docx)
    catalog = Path(args.catalog)
    mapping = Path(args.mapping)
    if not docx.exists():
        print(f"ERROR: not found: {docx}", file=sys.stderr)
        return 1
    if not catalog.exists():
        print(f"ERROR: --catalog not found: {catalog}", file=sys.stderr)
        return 1
    if not mapping.exists():
        print(f"ERROR: --mapping not found: {mapping}", file=sys.stderr)
        return 1

    try:
        process(docx, catalog, mapping)
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON 파싱 실패: {e}", file=sys.stderr)
        return 2
    except zipfile.BadZipFile as e:
        print(f"ERROR: docx zip 파싱 실패: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
