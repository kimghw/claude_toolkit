#!/usr/bin/env python3
"""
md2docx_pstyle/apply.py — decisions.json 을 받아 output docx 의 단락 pStyle/ind 정규화

설계:
    scan.py 의 보고서 → Claude AskUserQuestion → 사용자 결정으로 finalized 된
    decisions.json 을 입력으로 받아 in-place (또는 --out) 으로 docx 를 patch 한다.
    스캔 로직은 들어 있지 않다 — 짝꿍 scan.py 와 paragraph_indices 컨트랙트로만 연결.

paragraph_indices 의미:
    word/document.xml 안 모든 `<w:p ...>...</w:p>` 매치를 0-based 로 enumerate 한 인덱스.
    scan.py 와 정확히 같은 정규식을 써야 한다:
        re.finditer(r'<w:p\b[^>]*>.*?</w:p>', xml, re.DOTALL)

action 별 동작:
    skip         — 손대지 않음.
    rename       — pStyle 을 target_style_id 로 set/replace.
                   (헤딩 그룹·styled 그룹의 정규화)
    list_apply   — pStyle 을 target_style_id (보통 List Paragraph 계열) 로 set/replace.
                   ind_left / ind_leftChars / ind_hangingChars 가 있으면 <w:ind> 설정.
                   strip_numpr=true 면 <w:numPr> 제거.
    marker_ind   — pStyle 변경 없이 <w:ind> 만 target hierarchy 값으로 set.
                   마커 텍스트는 손대지 않음 (회사 양식 그대로 보이게 들여쓰기만 맞춤).

엣지 케이스:
    - <w:pPr> 없음                 → 필요 시 새로 삽입
    - <w:pPr/> self-closing       → 정상 형태로 expand 후 자식 삽입
    - 인덱스가 문서 단락 수보다 큼 → 경고 후 skip
    - 같은 인덱스 중복 지정        → 마지막 decision 이 이김

CLI:
    python apply.py <output.docx> <decisions.json>
    python apply.py <output.docx> <decisions.json> --out <patched.docx>

종료 코드:
    0 = 성공
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


# ---------------------------------------------------------------------------
# 정규식 — XML patch 컨벤션 (이전 md2docx_layout/apply_lists.py 에서 통합)
# ---------------------------------------------------------------------------

PARA_RE          = re.compile(r'<w:p\b[^>]*>.*?</w:p>', re.DOTALL)
PARA_OPEN_RE     = re.compile(r'<w:p\b[^>]*>')
PPR_BLOCK_RE     = re.compile(r'<w:pPr>(.*?)</w:pPr>', re.DOTALL)
PPR_SELFCLOSE_RE = re.compile(r'<w:pPr\s*/>')
PSTYLE_RE        = re.compile(r'<w:pStyle\s+[^/>]*?/>')
NUMPR_RE         = re.compile(r'<w:numPr>.*?</w:numPr>', re.DOTALL)
NUMPR_SELFCLOSE_RE = re.compile(r'<w:numPr\s*/>')
IND_RE           = re.compile(r'<w:ind\s+[^/>]*?/>')
RPR_BLOCK_RE     = re.compile(r'<w:rPr>.*?</w:rPr>', re.DOTALL)
RPR_SELFCLOSE_RE = re.compile(r'<w:rPr\s*/>')


# ---------------------------------------------------------------------------
# pPr 조작 헬퍼
# ---------------------------------------------------------------------------

def _expand_self_closing_ppr(para_xml: str) -> str:
    return PPR_SELFCLOSE_RE.sub('<w:pPr></w:pPr>', para_xml, count=1)


def _ensure_ppr(para_xml: str) -> str:
    if PPR_SELFCLOSE_RE.search(para_xml):
        return _expand_self_closing_ppr(para_xml)
    if PPR_BLOCK_RE.search(para_xml):
        return para_xml
    m = PARA_OPEN_RE.match(para_xml)
    if not m:
        return para_xml
    return para_xml[:m.end()] + '<w:pPr></w:pPr>' + para_xml[m.end():]


def _get_ppr_inner(para_xml: str) -> str | None:
    m = PPR_BLOCK_RE.search(para_xml)
    return m.group(1) if m else None


def _set_ppr_inner(para_xml: str, new_inner: str) -> str:
    para_xml = _ensure_ppr(para_xml)
    return PPR_BLOCK_RE.sub(
        lambda m: f'<w:pPr>{new_inner}</w:pPr>',
        para_xml, count=1,
    )


def _set_pstyle(ppr_inner: str, style_val: str) -> str:
    pstyle_xml = f'<w:pStyle w:val="{style_val}"/>'
    if PSTYLE_RE.search(ppr_inner):
        return PSTYLE_RE.sub(pstyle_xml, ppr_inner, count=1)
    return pstyle_xml + ppr_inner


def _remove_numpr(ppr_inner: str) -> str:
    ppr_inner = NUMPR_RE.sub('', ppr_inner)
    ppr_inner = NUMPR_SELFCLOSE_RE.sub('', ppr_inner)
    return ppr_inner


def _set_ind(ppr_inner: str,
             ind_left: int | None,
             ind_leftChars: int | None,
             ind_hangingChars: int | None) -> str:
    attrs = []
    if ind_left is not None:
        attrs.append(f'w:left="{ind_left}"')
    if ind_leftChars is not None:
        attrs.append(f'w:leftChars="{ind_leftChars}"')
    if ind_hangingChars is not None:
        attrs.append(f'w:hangingChars="{ind_hangingChars}"')
    if not attrs:
        return ppr_inner
    ind_xml = f'<w:ind {" ".join(attrs)}/>'
    if IND_RE.search(ppr_inner):
        return IND_RE.sub(ind_xml, ppr_inner, count=1)
    rpr_m = RPR_BLOCK_RE.search(ppr_inner)
    if rpr_m:
        return ppr_inner[:rpr_m.start()] + ind_xml + ppr_inner[rpr_m.start():]
    rpr_sc_m = RPR_SELFCLOSE_RE.search(ppr_inner)
    if rpr_sc_m:
        return ppr_inner[:rpr_sc_m.start()] + ind_xml + ppr_inner[rpr_sc_m.start():]
    return ppr_inner + ind_xml


# ---------------------------------------------------------------------------
# action 핸들러
# ---------------------------------------------------------------------------

def apply_rename(para_xml: str, target_style_id: str) -> str:
    para_xml = _ensure_ppr(para_xml)
    inner = _get_ppr_inner(para_xml) or ''
    inner = _set_pstyle(inner, target_style_id)
    return _set_ppr_inner(para_xml, inner)


def apply_list_apply(para_xml: str,
                     target_style_id: str,
                     ind_left: int | None,
                     ind_leftChars: int | None,
                     ind_hangingChars: int | None,
                     strip_numpr: bool) -> str:
    para_xml = _ensure_ppr(para_xml)
    inner = _get_ppr_inner(para_xml) or ''
    inner = _set_pstyle(inner, target_style_id)
    if strip_numpr:
        inner = _remove_numpr(inner)
    if ind_left is not None or ind_leftChars is not None or ind_hangingChars is not None:
        inner = _set_ind(inner, ind_left, ind_leftChars, ind_hangingChars)
    return _set_ppr_inner(para_xml, inner)


def apply_marker_ind(para_xml: str,
                     ind_left: int | None,
                     ind_leftChars: int | None,
                     ind_hangingChars: int | None) -> str:
    para_xml = _ensure_ppr(para_xml)
    inner = _get_ppr_inner(para_xml) or ''
    inner = _set_ind(inner, ind_left, ind_leftChars, ind_hangingChars)
    return _set_ppr_inner(para_xml, inner)


def apply_marker_replace(para_xml: str,
                         marker: str,
                         leading_ws: str,
                         ind_left: int | None,
                         ind_leftChars: int | None,
                         ind_hangingChars: int | None,
                         target_ppr_inner: str | None = None,
                         target_marker_rpr: str | None = None) -> str:
    """numPr 제거 + (target pPr 복사 또는 ind 설정) + 단락 본문 앞에 마커 텍스트 run 삽입.

    target_ppr_inner 가 주어지면 단락의 pPr 내부를 그것으로 통째 교체 (pStyle / spacing /
    jc 등 사용자 양식 마커 단락의 단락 서식을 그대로 복사). numPr 은 잔재가 있으면 제거.
    주어지지 않으면 fallback 으로 ind 만 설정 (이전 동작).

    target_marker_rpr 가 주어지면 마커 텍스트 run 에 rPr 로 적용 (폰트/크기/굵기 등).
    decimal/bullet 그룹을 target marker_hierarchy 의 문자로 강제 교체할 때 사용.
    """
    para_xml = _ensure_ppr(para_xml)
    if target_ppr_inner is not None:
        new_inner = _remove_numpr(target_ppr_inner)
    else:
        inner = _get_ppr_inner(para_xml) or ''
        inner = _remove_numpr(inner)
        inner = _set_ind(inner, ind_left, ind_leftChars, ind_hangingChars)
        new_inner = inner
    para_xml = _set_ppr_inner(para_xml, new_inner)
    # pPr 닫는 태그 직후에 marker text run 삽입
    # 마커는 기본 색(검정)으로 — target rPr 에서 w:color 제거
    sanitized_rpr = re.sub(r'<w:color\s+[^/>]*/>', '', target_marker_rpr) if target_marker_rpr else ''
    rpr_block = f'<w:rPr>{sanitized_rpr}</w:rPr>' if sanitized_rpr else ''
    marker_run = (
        f'<w:r>{rpr_block}'
        '<w:t xml:space="preserve">'
        f'{leading_ws}{marker} '
        '</w:t></w:r>'
    )
    m = re.search(r'</w:pPr>', para_xml)
    if m:
        idx = m.end()
        para_xml = para_xml[:idx] + marker_run + para_xml[idx:]
    return para_xml


# ---------------------------------------------------------------------------
# document.xml 처리
# ---------------------------------------------------------------------------

def _split_paragraphs(doc_xml: str) -> tuple[list[str], list[str]]:
    paragraphs: list[str] = []
    separators: list[str] = []
    last_end = 0
    for m in PARA_RE.finditer(doc_xml):
        separators.append(doc_xml[last_end:m.start()])
        paragraphs.append(m.group(0))
        last_end = m.end()
    separators.append(doc_xml[last_end:])
    return paragraphs, separators


def _rejoin_paragraphs(paragraphs: list[str], separators: list[str]) -> str:
    parts: list[str] = []
    for sep, para in zip(separators, paragraphs):
        parts.append(sep)
        parts.append(para)
    parts.append(separators[-1])
    return ''.join(parts)


def _apply_decision(para_xml: str, decision: dict) -> tuple[str, str]:
    action = decision.get('action', 'skip')
    if action == 'skip':
        return para_xml, 'skip'
    if action == 'rename':
        tsid = decision.get('target_style_id')
        if not tsid:
            return para_xml, 'invalid:rename_missing_style_id'
        return apply_rename(para_xml, tsid), 'rename'
    if action == 'list_apply':
        tsid = decision.get('target_style_id')
        if not tsid:
            return para_xml, 'invalid:list_apply_missing_style_id'
        return apply_list_apply(
            para_xml,
            target_style_id=tsid,
            ind_left=decision.get('ind_left'),
            ind_leftChars=decision.get('ind_leftChars'),
            ind_hangingChars=decision.get('ind_hangingChars'),
            strip_numpr=bool(decision.get('strip_numpr', False)),
        ), 'list_apply'
    if action == 'marker_ind':
        return apply_marker_ind(
            para_xml,
            ind_left=decision.get('ind_left'),
            ind_leftChars=decision.get('ind_leftChars'),
            ind_hangingChars=decision.get('ind_hangingChars'),
        ), 'marker_ind'
    if action == 'marker_replace':
        marker = decision.get('marker')
        if not marker:
            return para_xml, 'invalid:marker_replace_missing_marker'
        return apply_marker_replace(
            para_xml,
            marker=marker,
            leading_ws=decision.get('leading_ws', ''),
            ind_left=decision.get('ind_left'),
            ind_leftChars=decision.get('ind_leftChars'),
            ind_hangingChars=decision.get('ind_hangingChars'),
            target_ppr_inner=decision.get('target_ppr_inner'),
            target_marker_rpr=decision.get('target_marker_rpr'),
        ), 'marker_replace'
    return para_xml, f'unknown:{action}'


def process_document_xml(doc_xml: str, decisions: list[dict]) -> tuple[str, dict]:
    paragraphs, separators = _split_paragraphs(doc_xml)
    n_para = len(paragraphs)
    counts = {
        'rename': 0,
        'list_apply': 0,
        'marker_ind': 0,
        'marker_replace': 0,
        'skip': 0,
        'missing': 0,
        'invalid': 0,
        'unknown': 0,
    }
    touched: list[int] = []
    warnings: list[str] = []

    for d in decisions:
        gid = d.get('group_id', '?')
        indices = d.get('paragraph_indices', [])
        action = d.get('action', 'skip')

        for idx in indices:
            if not isinstance(idx, int) or idx < 0 or idx >= n_para:
                counts['missing'] += 1
                warnings.append(
                    f"[APPLY-LINE-WARN] group={gid} idx={idx} 범위 밖 (문서 단락 {n_para}개) — skip"
                )
                continue
            new_para, eff = _apply_decision(paragraphs[idx], d)
            if eff == 'skip':
                counts['skip'] += 1
                continue
            if eff.startswith('invalid:'):
                counts['invalid'] += 1
                warnings.append(
                    f"[APPLY-LINE-WARN] group={gid} idx={idx} {eff} — skip"
                )
                continue
            if eff.startswith('unknown:'):
                counts['unknown'] += 1
                warnings.append(
                    f"[APPLY-LINE-WARN] group={gid} idx={idx} 알 수 없는 action={action} — skip"
                )
                continue
            paragraphs[idx] = new_para
            counts[eff] += 1
            touched.append(idx)

    new_doc = _rejoin_paragraphs(paragraphs, separators)
    return new_doc, {
        'counts': counts,
        'touched_indices': sorted(set(touched)),
        'warnings': warnings,
        'total_paragraphs': n_para,
    }


# ---------------------------------------------------------------------------
# zipfile round-trip
# ---------------------------------------------------------------------------

def apply_to_docx(docx_in: Path, docx_out: Path, decisions: list[dict]) -> dict:
    with zipfile.ZipFile(docx_in) as zin:
        names = zin.namelist()
        contents = {n: zin.read(n) for n in names}

    if 'word/document.xml' not in contents:
        raise RuntimeError(f"word/document.xml not in {docx_in}")

    doc_xml = contents['word/document.xml'].decode('utf-8')
    new_doc, info = process_document_xml(doc_xml, decisions)
    contents['word/document.xml'] = new_doc.encode('utf-8')

    with zipfile.ZipFile(docx_out, 'w', zipfile.ZIP_DEFLATED) as zout:
        for name in names:
            zout.writestr(name, contents[name])

    info['output_path'] = str(docx_out)
    info['output_size'] = docx_out.stat().st_size
    return info


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_decisions(path: Path) -> list[dict]:
    with path.open(encoding='utf-8') as f:
        data = json.load(f)
    decisions = data.get('decisions')
    if not isinstance(decisions, list):
        raise ValueError(f"decisions.json: 'decisions' 키가 list 가 아님 ({path})")
    return decisions


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        description="decisions.json 을 받아 output docx 의 단락 pStyle/ind 정규화"
    )
    ap.add_argument('docx', help="대상 output docx (in-place 또는 --out 지정)")
    ap.add_argument('decisions', help="finalized decisions.json 경로")
    ap.add_argument('--out', help="별도 출력 경로 (기본: in-place)")
    args = ap.parse_args()

    inp = Path(args.docx)
    dec_path = Path(args.decisions)
    if not inp.exists():
        print(f"[APPLY-LINE] ERROR: docx not found: {inp}", file=sys.stderr)
        return 1
    if not dec_path.exists():
        print(f"[APPLY-LINE] ERROR: decisions.json not found: {dec_path}", file=sys.stderr)
        return 1

    try:
        decisions = _load_decisions(dec_path)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[APPLY-LINE] ERROR: decisions.json 파싱 실패: {e}", file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else inp

    if out.resolve() == inp.resolve():
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            info = apply_to_docx(inp, tmp_path, decisions)
            shutil.move(str(tmp_path), str(inp))
            info['output_path'] = str(inp)
            info['output_size'] = inp.stat().st_size
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        loc = "in-place"
    else:
        info = apply_to_docx(inp, out, decisions)
        loc = str(out)

    c = info['counts']
    print(f"[APPLY-LINE] {inp.name}: 단락 {info['total_paragraphs']}개 중 "
          f"rename={c['rename']} list_apply={c['list_apply']} marker_ind={c['marker_ind']} "
          f"marker_replace={c['marker_replace']} skip={c['skip']} missing={c['missing']} "
          f"invalid={c['invalid']} unknown={c['unknown']}")
    print(f"[APPLY-LINE] 패치된 인덱스: {info['touched_indices']}")
    for w in info['warnings']:
        print(f"      {w}")
    print(f"[APPLY-LINE] 저장: {loc} ({info['output_size']} bytes)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
