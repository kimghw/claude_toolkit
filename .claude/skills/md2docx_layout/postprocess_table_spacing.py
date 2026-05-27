#!/usr/bin/env python3
"""
md2docx_layout/postprocess_table_spacing.py — 표 직후 단락 간격 강제 적용

문제:
    pandoc 출력 docx 는 보통 </w:tbl> 다음에 곧바로 다음 콘텐츠(헤딩/단락)이 오거나
    빈 단락 한 개만 두는데, 회사 양식 기본 단락 간격으로는 표가 다음 텍스트와 너무
    붙어 보인다. Word UI 에서 "표 다음 빈 단락을 클릭해 단락 앞/뒤 간격 조정" 하는
    수작업을 자동화한다.

해결:
    document.xml 의 모든 top-level <w:tbl> 닫힘 직후에 대해:
        mode='ensure' (기본):
            다음 sibling 이 빈 <w:p> 면 → 그 단락의 <w:pPr><w:spacing> 패치
            아니면 → 새 빈 <w:p> 를 삽입 (설정된 spacing 박힌 채로)
        mode='insert':
            항상 새 빈 단락 삽입
        mode='patch_existing':
            다음 sibling 이 빈 <w:p> 일 때만 patch (없으면 무시)

    셀 내부 nested table 은 skip_nested_tables=true 면 건너뜀.

설정:
    .claude/skills/md2docx_layout/settings.json 의 "post_table_spacing" 섹션

Usage:
    python postprocess_table_spacing.py <output.docx>                 # in-place
    python postprocess_table_spacing.py <output.docx> --out <new>
    python postprocess_table_spacing.py <output.docx> --settings <path.json>
    python postprocess_table_spacing.py <output.docx> --dry-run       # 대상 위치만 보고

종료 코드:
    0 = 성공 (비활성/스킵 포함)
    1 = 실행 오류
"""

import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_SETTINGS_PATH = SKILL_DIR / "settings.json"


# top-level body 안 element 식별용 — w:body 내부에서 w:tbl, w:tc, w:p 의 open/close 만 추적
# 셀(w:tc) 안에 들어가면 depth ≥ 1, top-level 은 0
TOKEN_RE = re.compile(r'<(/?)w:(tbl|tc|p)\b([^>]*)>')
WP_BLOCK_RE = re.compile(r'<w:p\b[^>]*>.*?</w:p>', re.DOTALL)
# self-closing <w:p .../> 만 매칭 — open-tag 안에서만 `/>` 를 찾도록 [^>]* 사용.
# `[^/]*` 로 쓰면 paragraph 안 nested 자체닫힘 (<w:pStyle .../>) 까지 빨아당겨 잘못 매칭됨.
WP_SELFCLOSE_RE = re.compile(r'<w:p\b[^>]*/>')
WT_RE = re.compile(r'<w:t\b[^>]*>([^<]*)</w:t>')
SPACING_RE = re.compile(r'<w:spacing\b[^/]*/>')
PPR_RE = re.compile(r'<w:pPr>(.*?)</w:pPr>', re.DOTALL)
PPR_SELFCLOSE_RE = re.compile(r'<w:pPr\s*/>')


def build_spacing_attr(cfg: dict) -> str:
    """spacing_before_twips / spacing_after_twips / line_twips / line_rule 로
    <w:spacing .../> 문자열 빌드. None 인 속성은 생략."""
    attrs = []
    before = cfg.get("spacing_before_twips")
    after = cfg.get("spacing_after_twips")
    line = cfg.get("line_twips")
    rule = cfg.get("line_rule")
    if before is not None:
        attrs.append(f'w:before="{int(before)}"')
    if after is not None:
        attrs.append(f'w:after="{int(after)}"')
    if line is not None:
        attrs.append(f'w:line="{int(line)}"')
        if rule:
            attrs.append(f'w:lineRule="{rule}"')
    if not attrs:
        return ""
    return f'<w:spacing {" ".join(attrs)}/>'


def new_empty_paragraph(spacing_xml: str) -> str:
    if not spacing_xml:
        return '<w:p/>'
    return f'<w:p><w:pPr>{spacing_xml}</w:pPr></w:p>'


def is_empty_paragraph(p_xml: str) -> bool:
    """단락 안에 텍스트가 없으면 빈 단락. <w:t> 내용 strip 후 빈 문자열이면 empty."""
    texts = WT_RE.findall(p_xml)
    return all(t.strip() == "" for t in texts)


def patch_paragraph_spacing(p_xml: str, spacing_xml: str) -> str:
    """단락의 <w:pPr> 안 <w:spacing> 을 spacing_xml 로 교체. 없으면 추가. pPr 자체가 없으면 생성."""
    if not spacing_xml:
        return p_xml

    # 1) pPr 가 있는 경우
    ppr_m = PPR_RE.search(p_xml)
    if ppr_m:
        inner = ppr_m.group(1)
        if SPACING_RE.search(inner):
            new_inner = SPACING_RE.sub(spacing_xml, inner, count=1)
        else:
            new_inner = spacing_xml + inner
        new_ppr = f"<w:pPr>{new_inner}</w:pPr>"
        return p_xml[: ppr_m.start()] + new_ppr + p_xml[ppr_m.end():]

    # 2) self-closing pPr
    sm = PPR_SELFCLOSE_RE.search(p_xml)
    if sm:
        return p_xml[: sm.start()] + f"<w:pPr>{spacing_xml}</w:pPr>" + p_xml[sm.end():]

    # 3) pPr 가 아예 없는 경우 — <w:p> 또는 <w:p ...> 직후에 삽입
    op_m = re.match(r'<w:p\b[^>]*>', p_xml)
    if op_m:
        return p_xml[: op_m.end()] + f"<w:pPr>{spacing_xml}</w:pPr>" + p_xml[op_m.end():]

    return p_xml


def find_top_level_table_close_positions(doc_xml: str) -> list[int]:
    """document.xml 에서 top-level (w:tc 외부) <w:tbl> 의 </w:tbl> 끝 위치 리스트.
    nested table 닫힘은 제외.

    Returns: list of int (각 </w:tbl> 의 직후 위치 = m.end())
    """
    positions = []
    tc_depth = 0
    tbl_stack = []  # 각 항목은 그 tbl 이 열렸을 때의 tc_depth

    for m in TOKEN_RE.finditer(doc_xml):
        is_close = (m.group(1) == '/')
        tag = m.group(2)
        attrs = m.group(3)
        self_close = attrs.endswith('/')

        if tag == 'tc':
            if not is_close and not self_close:
                tc_depth += 1
            elif is_close:
                tc_depth -= 1
        elif tag == 'tbl':
            if not is_close and not self_close:
                tbl_stack.append(tc_depth)
            elif is_close:
                opened_at = tbl_stack.pop() if tbl_stack else None
                if opened_at == 0:
                    positions.append(m.end())
        # w:p 는 depth 추적에 영향 없음 — 별도 처리

    return positions


# bookmark/comment/perm/proof 같은 inline-position 마커는 paragraph 사이에 자유롭게 끼어드는
# zero-render 요소들. 다음 paragraph 를 찾을 때 건너뛴다.
SKIPPABLE_MARKER_RE = re.compile(
    r'<w:(bookmarkStart|bookmarkEnd|commentRangeStart|commentRangeEnd|commentReference|'
    r'proofErr|permStart|permEnd|moveFromRangeStart|moveFromRangeEnd|'
    r'moveToRangeStart|moveToRangeEnd|customXmlInsRangeStart|customXmlInsRangeEnd|'
    r'customXmlDelRangeStart|customXmlDelRangeEnd|customXmlMoveFromRangeStart|'
    r'customXmlMoveFromRangeEnd|customXmlMoveToRangeStart|customXmlMoveToRangeEnd)\b[^>]*/?>'
)


def _skip_ws_and_markers(doc_xml: str, start: int) -> int:
    """start 부터 공백/줄바꿈/inline-position 마커(bookmark 등) 를 건너뛴 위치 반환."""
    i = start
    while i < len(doc_xml):
        # 공백
        while i < len(doc_xml) and doc_xml[i] in " \t\r\n":
            i += 1
        if i >= len(doc_xml):
            return i
        if doc_xml[i] != '<':
            return i
        # inline marker 인지 확인
        m = SKIPPABLE_MARKER_RE.match(doc_xml, i)
        if not m:
            return i
        i = m.end()
    return i


def find_next_paragraph(doc_xml: str, start: int) -> tuple[int, int, str] | None:
    """start 위치 이후의 다음 paragraph 가 <w:p>...</w:p> 이면 (insert_pos, end_idx, p_xml) 반환.
    공백·줄바꿈·bookmark/comment 마커는 건너뛴다. 첫 비-skippable 토큰이 <w:p> 가 아니면 None.

    insert_pos 는 새 단락을 삽입할 위치 (= paragraph 시작 위치, 마커들 뒤).
    self-closing <w:p/> 도 paragraph 로 인정.
    """
    i = _skip_ws_and_markers(doc_xml, start)
    if i >= len(doc_xml) or doc_xml[i] != '<':
        return None

    # self-closing <w:p/> 먼저 시도
    sm = WP_SELFCLOSE_RE.match(doc_xml, i)
    if sm:
        return (sm.start(), sm.end(), sm.group(0))

    # <w:p ...>...</w:p>
    if not doc_xml.startswith('<w:p', i):
        return None
    m = WP_BLOCK_RE.match(doc_xml, i)
    if m:
        return (m.start(), m.end(), m.group(0))
    return None


def apply_post_table_spacing(doc_xml: str, cfg: dict) -> tuple[str, dict]:
    """document.xml 에 post_table_spacing 설정 적용.

    Returns: (new_doc_xml, stats)
        stats = {
            'top_level_tables': N,
            'patched': N,    # 기존 빈 단락에 spacing 박은 개수
            'inserted': N,   # 새 빈 단락 삽입한 개수
            'skipped_nonempty': N,  # mode='patch_existing' 인데 다음이 비어있지 않아 skip
        }
    """
    mode = cfg.get("mode", "ensure")
    if mode == "off" or not cfg.get("enabled", True):
        return doc_xml, {'top_level_tables': 0, 'patched': 0, 'inserted': 0, 'skipped_nonempty': 0}

    spacing_xml = build_spacing_attr(cfg)
    if not spacing_xml:
        return doc_xml, {'top_level_tables': 0, 'patched': 0, 'inserted': 0, 'skipped_nonempty': 0}

    skip_nested = cfg.get("skip_nested_tables", True)
    if skip_nested:
        positions = find_top_level_table_close_positions(doc_xml)
    else:
        # 모든 </w:tbl> 닫힘
        positions = [m.end() for m in re.finditer(r'</w:tbl>', doc_xml)]

    stats = {'top_level_tables': len(positions), 'patched': 0, 'inserted': 0, 'skipped_nonempty': 0}
    if not positions:
        return doc_xml, stats

    # 뒤에서부터 처리 (앞 인덱스 보존)
    new_doc = doc_xml
    for pos in reversed(positions):
        if mode == "insert":
            # 항상 삽입 — bookmark 마커 뒤로 자연스럽게 밀어 넣음
            insert_pos = _skip_ws_and_markers(new_doc, pos)
            new_p = new_empty_paragraph(spacing_xml)
            new_doc = new_doc[:insert_pos] + new_p + new_doc[insert_pos:]
            stats['inserted'] += 1
            continue

        nxt = find_next_paragraph(new_doc, pos)
        if nxt is None:
            # 다음 sibling 이 paragraph 가 아님 (다른 table, sectPr, end-of-body 등)
            if mode == "patch_existing":
                continue
            # ensure: 마커 뒤에 새 빈 단락 삽입
            insert_pos = _skip_ws_and_markers(new_doc, pos)
            new_p = new_empty_paragraph(spacing_xml)
            new_doc = new_doc[:insert_pos] + new_p + new_doc[insert_pos:]
            stats['inserted'] += 1
            continue

        p_start, p_end, p_xml = nxt
        if is_empty_paragraph(p_xml):
            # 빈 단락 — patch
            new_p = patch_paragraph_spacing(p_xml, spacing_xml)
            new_doc = new_doc[:p_start] + new_p + new_doc[p_end:]
            stats['patched'] += 1
        else:
            # 비어있지 않은 단락
            if mode == "patch_existing":
                stats['skipped_nonempty'] += 1
                continue
            # ensure: 비어있지 않은 단락 바로 앞에 새 빈 단락 삽입 (마커 뒤)
            new_p = new_empty_paragraph(spacing_xml)
            new_doc = new_doc[:p_start] + new_p + new_doc[p_start:]
            stats['inserted'] += 1

    return new_doc, stats


def load_settings(settings_path: Path) -> dict:
    """settings.json 로드. 없으면 빈 dict 반환."""
    if not settings_path.exists():
        return {}
    with open(settings_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


def postprocess(docx_in: Path, docx_out: Path, settings: dict) -> dict:
    """Returns: {'status': 'ok'|'disabled', 'stats': {...}, 'mode': ...}"""
    cfg = settings.get("post_table_spacing", {})
    if not cfg.get("enabled", True) or cfg.get("mode") == "off":
        if docx_in.resolve() != docx_out.resolve():
            shutil.copyfile(str(docx_in), str(docx_out))
        return {'status': 'disabled', 'stats': {}, 'mode': cfg.get('mode', 'off')}

    with zipfile.ZipFile(docx_in) as zin:
        names = zin.namelist()
        contents = {n: zin.read(n) for n in names}

    doc_xml = contents['word/document.xml'].decode('utf-8')
    new_doc, stats = apply_post_table_spacing(doc_xml, cfg)
    contents['word/document.xml'] = new_doc.encode('utf-8')

    with zipfile.ZipFile(docx_out, 'w', zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, contents[name])

    return {'status': 'ok', 'stats': stats, 'mode': cfg.get('mode', 'ensure')}


def main():
    ap = argparse.ArgumentParser(description="표 직후 단락 간격 강제 적용")
    ap.add_argument('docx', help="대상 docx (in-place 또는 --out 지정)")
    ap.add_argument('--out', help="별도 출력 경로 (기본: in-place)")
    ap.add_argument('--settings', help=f"settings.json 경로 (기본: {DEFAULT_SETTINGS_PATH})")
    ap.add_argument('--dry-run', action='store_true', help="패치 안 하고 대상 개수만 보고")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

    inp = Path(args.docx)
    if not inp.exists():
        print(f"ERROR: not found: {inp}", file=sys.stderr)
        return 1

    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS_PATH
    settings = load_settings(settings_path)
    cfg = settings.get("post_table_spacing", {})

    if args.dry_run:
        try:
            with zipfile.ZipFile(inp) as z:
                doc_xml = z.read('word/document.xml').decode('utf-8')
        except (KeyError, FileNotFoundError):
            print(f"[POSTPROCESS-TBLSP-DRY] document.xml 읽기 실패")
            return 0
        skip_nested = cfg.get("skip_nested_tables", True)
        if skip_nested:
            positions = find_top_level_table_close_positions(doc_xml)
        else:
            positions = [m.end() for m in re.finditer(r'</w:tbl>', doc_xml)]
        empty = 0
        nonempty = 0
        absent = 0
        for pos in positions:
            nxt = find_next_paragraph(doc_xml, pos)
            if nxt is None:
                absent += 1
            elif is_empty_paragraph(nxt[2]):
                empty += 1
            else:
                nonempty += 1
        mode = cfg.get('mode', 'ensure')
        print(f"[POSTPROCESS-TBLSP-DRY] top-level tables={len(positions)}, "
              f"next-sibling: empty-p={empty}, nonempty-p={nonempty}, other={absent}; mode={mode}")
        return 0

    if not cfg.get('enabled', True) or cfg.get('mode') == 'off':
        print(f"[POSTPROCESS-TBLSP] 비활성 (enabled=false 또는 mode=off) — 변경 없음")
        return 0

    out = Path(args.out) if args.out else inp

    def do(in_path, out_path):
        return postprocess(in_path, out_path, settings=settings)

    if out.resolve() == inp.resolve():
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            info = do(inp, tmp_path)
            shutil.move(str(tmp_path), str(inp))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        loc = "in-place"
    else:
        info = do(inp, out)
        loc = str(out.name)

    if info['status'] == 'ok':
        s = info['stats']
        before = cfg.get('spacing_before_twips')
        after = cfg.get('spacing_after_twips')
        line = cfg.get('line_twips')
        rule = cfg.get('line_rule')
        bits = []
        if before is not None: bits.append(f"before={before}")
        if after is not None: bits.append(f"after={after}")
        if line is not None: bits.append(f"line={line}({rule})")
        spec = ", ".join(bits) if bits else "(빈 spacing)"
        print(f"[POSTPROCESS-TBLSP] mode={info['mode']}, top-level 표 {s['top_level_tables']}개 "
              f"→ patched={s['patched']}, inserted={s['inserted']}, "
              f"skipped(nonempty)={s['skipped_nonempty']} ({loc})")
        print(f"[POSTPROCESS-TBLSP] spacing: {spec}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
