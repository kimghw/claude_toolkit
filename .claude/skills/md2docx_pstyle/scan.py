#!/usr/bin/env python3
"""
md2docx_pstyle/scan.py — target inventory + output pstyle_usage → JSON

목적:
    1) target.docx (회사 양식 raw) 에서 다음을 추출
        - heading_inventory : styles.xml 에서 heading 계열 (heading 1~9, Heading 1~9, 제목 1~9 등)
        - list_styles        : styles.xml 에서 List Paragraph 계열 (List Paragraph, 목록단락, ListNumber 등)
        - marker_hierarchy   : document.xml 의 마커(□ ○ - * (가) 1) 등) 단락에서 학습한
                               (marker, leading whitespace, ind_left, ind_leftChars) 의 level 부여
    2) output.docx (정규화 대상) 에서 단락별 사용 현황을 추출
        - pstyle_usage       : (idx, pStyle, has_numpr, numId/ilvl, marker, ind) → kind 별 그룹화
    3) JSON 보고서로 출력 — 다음 단계 (Claude AskUserQuestion + apply.py) 의 입력.

본 스크립트는 **수집만** 한다 — 어떤 docx 도 수정하지 않는다.

규약 (apply.py 와의 계약):
    paragraph_indices 는 output 의 word/document.xml 에서
    re.finditer(r'<w:p\b[^>]*>.*?</w:p>', xml, re.DOTALL) 로 열거한 0-based index.
    apply.py 도 동일한 정규식·동일한 순서로 열거해야 한다.

Usage:
    python scan.py <output.docx> --target <target.docx>
    python scan.py <output.docx> --target <target.docx> --out-report <json>

종료 코드:
    0 = 성공
    1 = 실행 오류
"""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Marker tokens (이전 md2docx_layout/scan_lists.py 의 어휘를 본 스킬로 통합·확장)
# ---------------------------------------------------------------------------

_SINGLE_CHAR_MARKERS = [
    "□", "■", "○", "●", "◯", "◎", "▪", "▫", "·", "-", "*",
]

# canonical 한국 문서 양식 bullet 우선순위 — level 1, 2, 3, ... 순서를 ind 값과 무관하게
# 이 순서대로 부여한다. target 에 일부만 있으면 해당 level 만 채우고 다른 level 은 비워둠.
# 예: target 본문에 □ 와 - 만 있으면 → level 1=□, level 3=-  (level 2=○ 공석)
#
# === SOURCE OF TRUTH ===
# 본 리스트가 canonical priority 의 **유일한 정의**다.
# references/list_types.md §3-B 의 표는 이 리스트의 mirror 로,
# 사람이 읽기 쉽게 두는 사본일 뿐 코드는 본 상수만 본다.
# 우선순위를 바꿀 땐 반드시 다음을 함께 갱신:
#   1) 본 리스트 (코드)
#   2) references/list_types.md §3-B 표 (문서)
# 둘이 어긋나면 코드(본 상수) 가 이긴다.
CANONICAL_BULLET_PRIORITY = [
    "□",   # level 1
    "○",   # level 2
    "-",   # level 3
    "▪",   # level 4
    "·",   # level 5
    "*",   # level 6
    "■",   # level 7
    "●",   # level 8
    "◯",   # level 9
    "◎",   # level 10
    "▫",   # level 11
]
_CIRCLED_DIGITS = [chr(c) for c in range(0x2460, 0x2473 + 1)]   # ①..⑳
_PAREN_HANGUL_LETTERS = [chr(c) for c in range(0x3200, 0x321E + 1)]  # ㈀..㈞

_COMPOUND_MARKER_PATTERNS = [
    r"\(\d+\)",
    r"\([가-힣]\)",
    r"[가-힣]\.",
    r"\d+\)",
]

_ALL_MARKER_ALT = (
    "(?:"
    + "|".join(re.escape(m) for m in _SINGLE_CHAR_MARKERS + _CIRCLED_DIGITS + _PAREN_HANGUL_LETTERS)
    + "|" + "|".join(_COMPOUND_MARKER_PATTERNS)
    + ")"
)

# (leading_ws) (marker) (공백+) 로 캡처 — leading_ws 보존이 본 스킬의 특징
MARKER_PREFIX_RE = re.compile(r"^(\s*)(" + _ALL_MARKER_ALT + r")\s+")


# ---------------------------------------------------------------------------
# OOXML regex
# ---------------------------------------------------------------------------

P_RE     = re.compile(r"<w:p\b[^>]*>.*?</w:p>", re.DOTALL)
WT_RE    = re.compile(r"<w:t(?:\s+[^>]*)?>([^<]*)</w:t>", re.DOTALL)
TAB_RE   = re.compile(r"<w:tab\s*/>")
BR_RE    = re.compile(r"<w:br\s*/>")
IND_RE   = re.compile(r"<w:ind\b[^/>]*/>")
NUMPR_RE = re.compile(r"<w:numPr>(.*?)</w:numPr>", re.DOTALL)
NUMID_RE = re.compile(r'<w:numId\s+w:val="([^"]+)"\s*/>')
ILVL_RE  = re.compile(r'<w:ilvl\s+w:val="([^"]+)"\s*/>')
PSTYLE_RE = re.compile(r'<w:pStyle\s+w:val="([^"]+)"\s*/>')

# 단락의 본문 영역(run 부분) 만 — pPr 안의 텍스트 노이즈를 피하기 위해 분리
# pPr 는 단락의 *처음* 에 있는 한 블록. 그 다음 부터가 run 영역.
PPR_BLOCK_RE = re.compile(r"<w:pPr>.*?</w:pPr>", re.DOTALL)


def _body_after_ppr(p_xml: str) -> str:
    """단락 XML 에서 pPr 블록을 제거한 본문 영역 반환.
    leading marker 추출 시 pPr 안 메타데이터 텍스트 노이즈를 배제."""
    m = PPR_BLOCK_RE.search(p_xml)
    if m:
        return p_xml[:m.start()] + p_xml[m.end():]
    return p_xml


def extract_visible_text(p_xml: str) -> str:
    """단락의 본문 텍스트를 <w:t> 순서대로 concat.
    <w:tab/> 는 \\t, <w:br/> 는 \\n 으로 표시 — leading_ws 학습이 탭/줄바꿈도 식별하도록.
    """
    body = _body_after_ppr(p_xml)
    # 모든 텍스트성 토큰 (w:t / w:tab / w:br) 을 등장 순서대로 모은다
    tokens = []
    for m in re.finditer(r"<w:t(?:\s+[^>]*)?>([^<]*)</w:t>|<w:tab\s*/>|<w:br\s*/>", body, re.DOTALL):
        s = m.group(0)
        if s.startswith("<w:tab"):
            tokens.append("\t")
        elif s.startswith("<w:br"):
            tokens.append("\n")
        else:
            tokens.append(m.group(1))
    return "".join(tokens)


def extract_ind_attrs(p_xml: str) -> dict:
    m = IND_RE.search(p_xml)
    if not m:
        return {}
    el = m.group(0)
    out = {}
    for key in ("left", "leftChars", "hanging", "hangingChars",
                "firstLine", "firstLineChars", "right", "rightChars"):
        mm = re.search(rf'w:{key}="(-?\d+)"', el)
        if mm:
            try:
                out[key] = int(mm.group(1))
            except ValueError:
                pass
    return out


def extract_pstyle(p_xml: str) -> str | None:
    m = PSTYLE_RE.search(p_xml)
    return m.group(1) if m else None


def extract_numpr(p_xml: str):
    m = NUMPR_RE.search(p_xml)
    if not m:
        return None
    inner = m.group(1)
    nid_m = NUMID_RE.search(inner)
    if not nid_m:
        return None
    ilvl_m = ILVL_RE.search(inner)
    return (nid_m.group(1), ilvl_m.group(1) if ilvl_m else "0")


def match_marker(text: str):
    """Returns (leading_ws, marker) or (None, None)."""
    m = MARKER_PREFIX_RE.match(text)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def truncate(s: str, n: int = 60) -> str:
    s = s.strip()
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


# ---------------------------------------------------------------------------
# target styles.xml 파싱
# ---------------------------------------------------------------------------

STYLE_RE = re.compile(r"<w:style\s+([^>]*?)>(.*?)</w:style>", re.DOTALL)

_HEADING_NAME_PATTERNS = [
    re.compile(r"^heading\s*\d+$", re.IGNORECASE),
    re.compile(r"^제목\s*\d+$"),
]

_LIST_NAME_PATTERNS = [
    re.compile(r"^list\s*paragraph$", re.IGNORECASE),
    re.compile(r"^목록\s*단락$"),
    re.compile(r"^list\s*number(?:\s*\d+)?$", re.IGNORECASE),
    re.compile(r"^list\s*bullet(?:\s*\d+)?$", re.IGNORECASE),
]

_STANDARD_NAME_PATTERNS = [
    re.compile(r"^normal$", re.IGNORECASE),
    re.compile(r"^standard$", re.IGNORECASE),
    re.compile(r"^표준$"),
    re.compile(r"^compact$", re.IGNORECASE),
    re.compile(r"^body\s*text(?:\s*\d+)?$", re.IGNORECASE),
    re.compile(r"^first\s*paragraph$", re.IGNORECASE),
    re.compile(r"^본문$"),
]


def _name_matches_any(name: str, patterns: list[re.Pattern]) -> bool:
    return any(p.match(name.strip()) for p in patterns)


def extract_target_styles(styles_xml: str) -> tuple[list, list, list]:
    """(heading_inventory, list_styles, standard_styles) 반환.

    heading_inventory : name 이 'heading N' / 'Heading N' / '제목 N' 패턴인 paragraph 스타일
    list_styles       : name 이 'List Paragraph' / '목록단락' / 'List Number' / 'List Bullet' 등
    standard_styles   : name 이 'Normal' / 'Standard' / '표준' / 'Compact' / 'Body Text' /
                        'First Paragraph' / '본문' 등 (본문/표준 계열)
    각 entry: {id, name, basedOn, default(bool), ind_left? (List 계열만)}
    """
    headings = []
    lists = []
    standards = []
    for m in STYLE_RE.finditer(styles_xml):
        attrs, body = m.group(1), m.group(2)
        sid_m = re.search(r'w:styleId="([^"]+)"', attrs)
        stype_m = re.search(r'w:type="([^"]+)"', attrs)
        default_m = re.search(r'w:default="([^"]+)"', attrs)
        name_m = re.search(r'<w:name\s+w:val="([^"]+)"', body)
        based_m = re.search(r'<w:basedOn\s+w:val="([^"]+)"', body)
        if not (sid_m and stype_m and name_m):
            continue
        sid = sid_m.group(1)
        stype = stype_m.group(1)
        name = name_m.group(1)
        based = based_m.group(1) if based_m else ""
        is_default = (default_m.group(1) == "1") if default_m else False
        if stype != "paragraph":
            continue
        if _name_matches_any(name, _HEADING_NAME_PATTERNS):
            headings.append({"id": sid, "name": name, "basedOn": based, "default": is_default})
            continue
        if _name_matches_any(name, _LIST_NAME_PATTERNS):
            ind_left = None
            ind_m = re.search(r'<w:ind\s+[^/>]*w:left="(-?\d+)"', body)
            if ind_m:
                try:
                    ind_left = int(ind_m.group(1))
                except ValueError:
                    pass
            lists.append({"id": sid, "name": name, "basedOn": based,
                          "default": is_default, "ind_left": ind_left})
            continue
        if _name_matches_any(name, _STANDARD_NAME_PATTERNS):
            standards.append({"id": sid, "name": name, "basedOn": based, "default": is_default})
    return headings, lists, standards


def extract_style_name_map(styles_xml: str) -> dict:
    """styles.xml 에서 styleId → name 매핑 추출.
    output 의 pStyle (styleId) 가 어떤 name 에 대응하는지 알기 위해."""
    out = {}
    for m in STYLE_RE.finditer(styles_xml):
        attrs, body = m.group(1), m.group(2)
        sid_m = re.search(r'w:styleId="([^"]+)"', attrs)
        name_m = re.search(r'<w:name\s+w:val="([^"]+)"', body)
        if sid_m and name_m:
            out[sid_m.group(1)] = name_m.group(1)
    return out


# ---------------------------------------------------------------------------
# numbering.xml → numId → (numFmt[ilvl=0], lvlText[ilvl=0])
# ---------------------------------------------------------------------------

NUM_RE = re.compile(r'<w:num\s+w:numId="(\d+)"[^>]*>(.*?)</w:num>', re.DOTALL)
ABSNUM_RE = re.compile(r'<w:abstractNum\s+w:abstractNumId="(\d+)"[^>]*>(.*?)</w:abstractNum>', re.DOTALL)
LVL_RE = re.compile(r'<w:lvl\s+w:ilvl="(\d+)"[^>]*>(.*?)</w:lvl>', re.DOTALL)


def extract_numid_numfmt_map(numbering_xml: str) -> dict:
    """numbering.xml → {numId: {ilvl: (numFmt, lvlText)}} 매핑.

    list 그룹 키를 (numId, ilvl) 대신 (numFmt, ilvl) 로 묶기 위함 —
    pandoc 이 같은 markdown 리스트라도 별개 numId 를 부여하므로,
    같은 modal numFmt 끼리 묶어 사용자 결정 횟수를 줄인다.
    """
    if not numbering_xml:
        return {}
    abs_map = {}  # abstractNumId → {ilvl: (numFmt, lvlText)}
    for am in ABSNUM_RE.finditer(numbering_xml):
        aid, body = am.group(1), am.group(2)
        levels = {}
        for lm in LVL_RE.finditer(body):
            ilvl_s, lbody = lm.group(1), lm.group(2)
            fmt_m = re.search(r'<w:numFmt\s+w:val="([^"]+)"', lbody)
            txt_m = re.search(r'<w:lvlText\s+w:val="([^"]*)"', lbody)
            levels[ilvl_s] = (fmt_m.group(1) if fmt_m else None,
                              txt_m.group(1) if txt_m else None)
        abs_map[aid] = levels

    out = {}
    for nm in NUM_RE.finditer(numbering_xml):
        nid, body = nm.group(1), nm.group(2)
        aid_m = re.search(r'<w:abstractNumId\s+w:val="(\d+)"', body)
        if not aid_m:
            continue
        aid = aid_m.group(1)
        out[nid] = abs_map.get(aid, {})
    return out


# ---------------------------------------------------------------------------
# target document.xml → marker_hierarchy 학습
# ---------------------------------------------------------------------------

def _extract_ppr_inner(p_xml: str) -> str:
    """단락 XML 에서 <w:pPr>...</w:pPr> 사이 내용 추출. 없으면 빈 문자열."""
    m = re.search(r"<w:pPr>(.*?)</w:pPr>", p_xml, re.DOTALL)
    return m.group(1) if m else ""


def _extract_marker_run_rpr(p_xml: str, marker: str) -> str:
    """단락 본문에서 마커 문자가 포함된 첫 run 의 rPr 내용 추출. 없으면 빈 문자열.

    마커 단락은 보통 본문 첫 run 에 마커 문자가 있다. 그 run 의 rPr 을 가져오면
    apply 시 같은 폰트/크기/굵기 등을 마커 텍스트에 그대로 입힐 수 있다.
    """
    body = _body_after_ppr(p_xml)
    # 첫 <w:r>...</w:r> 블록을 찾고, 그 안에서 마커 문자가 있는 <w:t> 가 있으면 그 run 의 rPr 채취
    run_iter = re.finditer(r"<w:r\b[^>]*>(.*?)</w:r>", body, re.DOTALL)
    for rm in run_iter:
        run_inner = rm.group(1)
        # 이 run 의 텍스트
        t_match = re.search(r"<w:t(?:\s+[^>]*)?>([^<]*)</w:t>", run_inner, re.DOTALL)
        if not t_match:
            continue
        if marker in t_match.group(1):
            rpr_m = re.search(r"<w:rPr>(.*?)</w:rPr>", run_inner, re.DOTALL)
            return rpr_m.group(1) if rpr_m else ""
    return ""


def learn_marker_hierarchy(target_doc_xml: str) -> list:
    """target.document.xml 의 마커 단락에서 (marker, leading_ws, ind, pPr, rPr) 학습.

    각 marker 의 첫 등장 단락 메타를 채집한 뒤, **CANONICAL_BULLET_PRIORITY** 순서에
    따라 level 1, 2, 3, ... 부여. target 에 없는 marker 의 level 자리는 빈 채로 보존
    (예: target 에 □ 와 - 만 있으면 level 1=□, level 3=-, level 2 는 결과에 없음 →
    md ilvl=1 (level 2) 이 들어오면 사용자/Claude 가 fallback 결정).

    canonical 에 없는 marker 는 priority 끝에 등장 순서대로 부여.

    entry 에 다음 정보 보존:
      - leading_ws : 마커 앞 공백
      - ind        : 들여쓰기 속성 (left, leftChars, hangingChars, hanging)
      - ppr_inner  : 단락 pPr 의 내부 XML (pStyle / spacing / jc 등) — apply 시 그대로 복사
      - marker_rpr : 마커 문자 run 의 rPr 내부 XML — apply 시 마커 run 의 폰트/크기 설정
    """
    seen = {}  # marker → first occurrence meta (한 marker 가 여러 ind 로 나타나면 첫 등장만)
    for p_xml in P_RE.findall(target_doc_xml):
        text = extract_visible_text(p_xml)
        ws, marker = match_marker(text)
        if not marker or marker in seen:
            continue
        ind = extract_ind_attrs(p_xml)
        seen[marker] = {
            "ind": ind,
            "leading_ws": ws or "",
            "ppr_inner": _extract_ppr_inner(p_xml),
            "marker_rpr": _extract_marker_run_rpr(p_xml, marker),
        }

    def _entry(marker: str, level: int) -> dict:
        meta = seen[marker]
        ind = meta["ind"]
        return {
            "level": level,
            "marker": marker,
            "ind_left": ind.get("left", 0),
            "ind_leftChars": ind.get("leftChars", 0),
            "ind_hangingChars": ind.get("hangingChars", 0),
            "leading_ws": meta["leading_ws"],
            "ppr_inner": meta["ppr_inner"],
            "marker_rpr": meta["marker_rpr"],
        }

    hierarchy = []
    used_markers = set()
    # canonical priority 순서대로 level 부여 (target 에 있는 것만 출력, 빈 level 은 skip)
    for lvl, m in enumerate(CANONICAL_BULLET_PRIORITY, start=1):
        if m in seen:
            hierarchy.append(_entry(m, lvl))
            used_markers.add(m)
    # canonical 에 없는 marker 는 priority 끝에 등장 순서로 추가
    next_level = len(CANONICAL_BULLET_PRIORITY) + 1
    for marker in seen:
        if marker not in used_markers:
            hierarchy.append(_entry(marker, next_level))
            next_level += 1
    return hierarchy


def _marker_to_levels(hierarchy: list) -> dict:
    out = {}
    for entry in hierarchy:
        out.setdefault(entry["marker"], []).append(entry)
    return out


def _assign_level(marker: str, ind: dict, m2l: dict) -> int | None:
    if marker not in m2l:
        return None
    cands = m2l[marker]
    if len(cands) == 1 or not ind:
        return cands[0]["level"]
    lc = ind.get("leftChars", 0)
    lf = ind.get("left", 0)
    best = min(cands, key=lambda c: (abs(c["ind_leftChars"] - lc), abs(c["ind_left"] - lf)))
    return best["level"]


# ---------------------------------------------------------------------------
# output.document.xml → pstyle_usage
# ---------------------------------------------------------------------------

def scan_output_pstyles(output_doc_xml: str, hierarchy: list,
                        output_style_names: dict | None = None,
                        numid_fmt_map: dict | None = None) -> list:
    r"""output 단락을 enumerate 하면서 kind 별 그룹화.

    분류 결정 우선순위 (계약 — apply.py 도 동일 가정):
        한 단락이 동시에 여러 조건을 만족할 수 있는 hybrid 라도
        다음 순서로 **하나의 kind 만** 부여한다.

            heading → list → marker → list_styled → standard → styled → plain

        - numPr 이 marker 보다 우선: <w:numPr> 는 Word 자동 번호의 구조적
          선언이라, 본문에 우연히 마커 비슷한 글자가 박혀 있어도 list 로 본다.
        - heading 이 numPr 보다 우선: 헤딩에 numPr 가 동시에 달리는 hybrid 가
          와도 heading 으로 분류해 사용자가 헤딩 매핑을 결정하게 한다.
        - marker 가 list_styled 보다 우선: 본문 글자에 마커가 박힌 단락은
          시각적 의미가 더 직접적 — list_styled(pStyle 만으로 List Paragraph
          계열 추정) 는 numPr 도 마커도 없을 때만 잡는다.

    kind (output_style_names 가 주어진 경우 pStyle → 실제 name 으로 해석):
        heading      : pStyle name 이 'heading N' / 'Heading N' / '제목 N' 매칭.
        list         : <w:numPr> 보유 (heading 이 아닐 때). 본문 마커 글자 유무는 무시.
        marker       : 본문이 마커 패턴으로 시작 (heading/numPr 둘 다 아닐 때).
        list_styled  : pStyle name 이 'List Paragraph' / '목록단락' / 'List Number' /
                       'List Bullet' 매칭. numPr 없는 List Paragraph 단락.
                       (보통 pandoc 이 List Paragraph 스타일만 박고 numPr 는 안 단 경우)
        standard     : pStyle name 이 'Normal' / 'Standard' / '표준' / 'Compact' /
                       'Body Text' / 'First Paragraph' / '본문' 매칭. 본문/표준 계열.
        styled       : 위 다 아니지만 명시 pStyle 보유 (사용자 결정 가능).
        plain        : 위 다 아님 — pStyle 도 없는 default 상속 단락. 그룹화하지 않음.
    """
    m2l = _marker_to_levels(hierarchy)
    style_names = output_style_names or {}
    nfmap = numid_fmt_map or {}

    def _resolve_name(sid: str | None) -> str:
        """pStyle (styleId) → human name. 매핑 없으면 styleId 자체 반환."""
        if not sid:
            return ""
        return style_names.get(sid, sid)

    def _resolve_numfmt(numid: str, ilvl: str) -> tuple[str, str]:
        """(numId, ilvl) → (numFmt, lvlText). numbering.xml 에 없으면 ('unknown', '')."""
        entry = nfmap.get(numid, {})
        if ilvl in entry:
            fmt, txt = entry[ilvl]
            return (fmt or "unknown", txt or "")
        return ("unknown", "")

    # 그룹 키: kind 별로 의미가 다름
    #   heading      : pStyle (styleId)
    #   list         : (numFmt, lvlText, ilvl) — pandoc 이 같은 markdown list 도 별개 numId 를 부여하므로,
    #                  같은 마커(numFmt + lvlText) + 같은 레벨끼리 묶어 사용자 결정 부담 감소.
    #                  같은 bullet 이라도 '•' vs '□' 는 다른 그룹, '%1.' vs '(%1)' 도 다른 그룹.
    #   marker       : (marker, level)
    #   list_styled  : pStyle (styleId) — List Paragraph 계열, numPr 없음
    #   standard     : pStyle (styleId) — 표준/본문 계열
    #   styled       : pStyle (styleId) — 그 외
    groups = {}  # key → {"kind", "members": [(idx, text)], "first": idx, "meta": dict}

    paragraphs = list(P_RE.finditer(output_doc_xml))

    for p_idx, m in enumerate(paragraphs):
        p_xml = m.group(0)
        text = extract_visible_text(p_xml)
        pstyle = extract_pstyle(p_xml)
        np = extract_numpr(p_xml)
        ws, marker = match_marker(text)
        ind = extract_ind_attrs(p_xml)
        pstyle_name = _resolve_name(pstyle)

        # 1) heading — pStyle 의 *해석된 name* 이 heading 패턴 또는 pStyle 자체가 'Heading\d+'
        is_heading = False
        if pstyle:
            if _name_matches_any(pstyle_name, _HEADING_NAME_PATTERNS):
                is_heading = True
            elif re.match(r"^(?:heading|Heading)\s*\d+$", pstyle) or re.match(r"^제목\s*\d+$", pstyle):
                is_heading = True
        if is_heading:
            key = ("heading", pstyle)
            meta = {"pstyle": pstyle, "pstyle_name": pstyle_name}
            kind = "heading"
        elif np:
            numfmt, lvltxt = _resolve_numfmt(np[0], np[1])
            key = ("list", numfmt, lvltxt, np[1])
            meta = {"numFmt": numfmt, "lvlText": lvltxt, "ilvl": np[1],
                    "numIds": [np[0]],
                    "pstyle": pstyle, "pstyle_name": pstyle_name}
            kind = "list"
        elif marker:
            level = _assign_level(marker, ind, m2l)
            key = ("marker", marker, level)
            meta = {"marker": marker, "level": level, "leading_ws": ws or "",
                    "pstyle": pstyle, "pstyle_name": pstyle_name}
            kind = "marker"
        elif pstyle and _name_matches_any(pstyle_name, _LIST_NAME_PATTERNS):
            key = ("list_styled", pstyle)
            meta = {"pstyle": pstyle, "pstyle_name": pstyle_name}
            kind = "list_styled"
        elif pstyle and _name_matches_any(pstyle_name, _STANDARD_NAME_PATTERNS):
            key = ("standard", pstyle)
            meta = {"pstyle": pstyle, "pstyle_name": pstyle_name}
            kind = "standard"
        elif pstyle:
            key = ("styled", pstyle)
            meta = {"pstyle": pstyle, "pstyle_name": pstyle_name}
            kind = "styled"
        else:
            continue  # plain 단락은 보고하지 않음

        bucket = groups.setdefault(key, {
            "kind": kind,
            "members": [],
            "first": p_idx,
            "meta": meta,
        })
        bucket["members"].append((p_idx, text))
        # list 그룹은 numFmt 기준으로 묶이므로 numIds 누적 추적
        if kind == "list" and "numIds" in meta:
            existing = bucket["meta"].setdefault("numIds", [])
            for nid in meta["numIds"]:
                if nid not in existing:
                    existing.append(nid)

    # 첫 등장 순으로 정렬 + group_id 부여
    sorted_groups = sorted(groups.values(), key=lambda g: g["first"])
    result = []
    counters = {"heading": 0, "list": 0, "marker": 0,
                "list_styled": 0, "standard": 0, "styled": 0}
    prefixes = {"heading": "H", "list": "L", "marker": "M",
                "list_styled": "LS", "standard": "STD", "styled": "S"}
    for g in sorted_groups:
        kind = g["kind"]
        counters[kind] += 1
        gid = f"{prefixes[kind]}{counters[kind]}"
        indices = [idx for idx, _ in g["members"]]
        samples = [truncate(t) for _, t in g["members"][:3]]
        entry = {
            "group_id": gid,
            "kind": kind,
            "paragraph_indices": indices,
            "samples": samples,
        }
        entry.update(g["meta"])
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# zipfile 헬퍼
# ---------------------------------------------------------------------------

def _read_xml(docx_path: Path, member: str) -> str:
    with zipfile.ZipFile(docx_path) as z:
        try:
            return z.read(member).decode("utf-8")
        except KeyError:
            return ""


def scan(output_path: Path, target_path: Path) -> dict:
    output_doc_xml = _read_xml(output_path, "word/document.xml")
    output_styles_xml = _read_xml(output_path, "word/styles.xml")
    output_numbering_xml = _read_xml(output_path, "word/numbering.xml")
    target_doc_xml = _read_xml(target_path, "word/document.xml")
    target_styles_xml = _read_xml(target_path, "word/styles.xml")

    heading_inv, list_styles, standard_styles = extract_target_styles(target_styles_xml)
    output_style_names = extract_style_name_map(output_styles_xml)
    numid_fmt_map = extract_numid_numfmt_map(output_numbering_xml)
    hierarchy = learn_marker_hierarchy(target_doc_xml)
    pstyle_usage = scan_output_pstyles(output_doc_xml, hierarchy,
                                       output_style_names, numid_fmt_map)

    return {
        "schema_version": 1,
        "target": str(target_path.resolve()),
        "output": str(output_path.resolve()),
        "heading_inventory": heading_inv,
        "list_styles": list_styles,
        "standard_styles": standard_styles,
        "marker_hierarchy": hierarchy,
        "pstyle_usage": pstyle_usage,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        description="target inventory + output pstyle_usage 를 추출해 JSON 보고서 생성"
    )
    ap.add_argument("output", help="대상 output docx (스캔만, 수정 안 함)")
    ap.add_argument("--target", required=True, help="target docx (회사 양식 raw)")
    ap.add_argument("--out-report", help="JSON 보고서 경로 (기본: cwd/output/<output_stem>_line.json — 단일 파일 덮어쓰기)")
    args = ap.parse_args()

    output_path = Path(args.output)
    target_path = Path(args.target)
    if not output_path.exists():
        print(f"[SCAN-LINE] ERROR: output not found: {output_path}", file=sys.stderr)
        return 1
    if not target_path.exists():
        print(f"[SCAN-LINE] ERROR: target not found: {target_path}", file=sys.stderr)
        return 1

    if args.out_report:
        report_path = Path(args.out_report)
    else:
        # 단일 파일 정책 — 같은 output 재스캔 시 덮어쓰기. 여러 버전 관리 안 함.
        report_path = Path.cwd() / "output" / f"{output_path.stem}_line.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        report = scan(output_path, target_path)
    except Exception as e:
        print(f"[SCAN-LINE] ERROR: scan failed: {e}", file=sys.stderr)
        return 1

    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    n_h = len(report["heading_inventory"])
    n_l = len(report["list_styles"])
    n_s = len(report["standard_styles"])
    n_m = len(report["marker_hierarchy"])
    by_kind = {"heading": 0, "list": 0, "marker": 0,
               "list_styled": 0, "standard": 0, "styled": 0}
    for g in report["pstyle_usage"]:
        by_kind[g["kind"]] = by_kind.get(g["kind"], 0) + 1

    print(f"[SCAN-LINE] target: {target_path.name}  → heading_inventory={n_h}, list_styles={n_l}, standard_styles={n_s}, marker_hierarchy={n_m}")
    if report["heading_inventory"]:
        for h in report["heading_inventory"]:
            based = h["basedOn"] or "(none)"
            d = " [default]" if h.get("default") else ""
            print(f"[SCAN-LINE]   heading : id={h['id']:<20} name='{h['name']}'  basedOn={based}{d}")
    if report["list_styles"]:
        for s in report["list_styles"]:
            ind = s.get("ind_left")
            ind_s = f"ind_left={ind}" if ind is not None else ""
            d = " [default]" if s.get("default") else ""
            print(f"[SCAN-LINE]   list    : id={s['id']:<20} name='{s['name']}'  {ind_s}{d}")
    if report["standard_styles"]:
        for s in report["standard_styles"]:
            based = s["basedOn"] or "(none)"
            d = " [default]" if s.get("default") else ""
            print(f"[SCAN-LINE]   standard: id={s['id']:<20} name='{s['name']}'  basedOn={based}{d}")
    if report["marker_hierarchy"]:
        for h in report["marker_hierarchy"]:
            ws_dbg = repr(h["leading_ws"]) if h["leading_ws"] else "''"
            print(f"[SCAN-LINE]   level {h['level']}: '{h['marker']}'  leading_ws={ws_dbg}  ind_left={h['ind_left']}  ind_leftChars={h['ind_leftChars']}")
    print(f"[SCAN-LINE] output: {output_path.name}  groups: heading={by_kind['heading']} list={by_kind['list']} marker={by_kind['marker']} list_styled={by_kind['list_styled']} standard={by_kind['standard']} styled={by_kind['styled']}")
    print(f"[SCAN-LINE] report: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
