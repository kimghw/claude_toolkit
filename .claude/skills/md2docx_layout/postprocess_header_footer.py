#!/usr/bin/env python3
"""
md2docx_layout/postprocess_header_footer.py — pandoc 변환 후 output docx 의
머리글/바닥글을 사용자 양식 docx (--source) 에서 가져온 텍스트 있는 한 쌍으로 교체.

스타일·numbering·document.xml 본문은 건드리지 않는다.
페이지 여백 (pgSz/pgMar 의 header/footer offset 포함) 동기화는 postprocess_page 의 책임.

알고리즘:
    1. --source 의 word/header*.xml, word/footer*.xml 중 텍스트가 있는 파일을 후보로
       삼아 각 그룹에서 텍스트 run 이 가장 많은 것을 선정 (header 0~1개, footer 0~1개).
    2. 선정된 xml + 그 _rels/*.rels + .rels 가 가리키는 word/media/* 를 모두 읽는다.
    3. output docx 의 zip 에서:
       a. 기존 word/header*.xml, word/footer*.xml 및 그 _rels/*.rels 전부 제거.
       b. [Content_Types].xml 의 header/footer Override 전부 제거 후 새것 추가.
       c. word/_rels/document.xml.rels 의 header/footer Relationship 전부 제거,
          새 rId 할당해 추가.
       d. word/document.xml 의 모든 sectPr 안 <w:headerReference>/<w:footerReference>
          모두 제거. 그런 다음 (비어 있지 않은 sectPr 마다) default header/footer
          참조를 주입.
       e. 새 header/footer XML + 그 .rels + media 를 zip 에 쓴다. media 파일명은
          출력 docx 의 기존 미디어와 충돌하지 않도록 'hf_' 접두를 붙이고 .rels 의
          Target 도 같이 재작성.

사용법:
    python postprocess_header_footer.py <output.docx> --source <ref.docx>
    python postprocess_header_footer.py <output.docx> --source <ref.docx> --out <new.docx>
    python postprocess_header_footer.py <output.docx> --source <ref.docx> --dry-run

종료 코드:
    0 = 성공 (source 없음·후보 없음 으로 스킵 포함)
    1 = 실행 오류
"""

import argparse
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


HEADER_FN_RE = re.compile(r'^word/header\d+\.xml$')
FOOTER_FN_RE = re.compile(r'^word/footer\d+\.xml$')
HEADER_RELS_RE = re.compile(r'^word/_rels/header\d+\.xml\.rels$')
FOOTER_RELS_RE = re.compile(r'^word/_rels/footer\d+\.xml\.rels$')

TEXT_RUN_RE = re.compile(r'<w:t[^>]*>([^<]*)</w:t>', re.DOTALL)
RELS_TARGET_RE = re.compile(r'\bTarget="([^"]+)"')

# sectPr 안 header/footer 참조
HDRREF_RE = re.compile(r'<w:headerReference\b[^/]*/>')
FTRREF_RE = re.compile(r'<w:footerReference\b[^/]*/>')
SECTPR_FULL_RE = re.compile(r'<w:sectPr\b[^>]*>.*?</w:sectPr>', re.DOTALL)
SECTPR_SELFCLOSE_RE = re.compile(r'<w:sectPr\b[^/]*/>')

# [Content_Types].xml 의 Override
CT_HDRFTR_OVERRIDE_RE = re.compile(
    r'<Override\b[^/]*ContentType="application/vnd\.openxmlformats-officedocument\.wordprocessingml\.(?:header|footer)\+xml"[^/]*/>'
)

# document.xml.rels 의 Relationship
DOCRELS_HDRFTR_REL_RE = re.compile(
    r'<Relationship\b[^/]*Type="http://schemas\.openxmlformats\.org/officeDocument/2006/relationships/(?:header|footer)"[^/]*/>'
)
DOCRELS_RID_RE = re.compile(r'\bId="rId(\d+)"')

HDR_CT = 'application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml'
FTR_CT = 'application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml'
HDR_REL_TYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/header'
FTR_REL_TYPE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer'


def count_text_chars(xml_bytes: bytes) -> int:
    """xml 안 <w:t> 의 비공백 문자 수 (없으면 0)."""
    try:
        s = xml_bytes.decode('utf-8', errors='replace')
    except Exception:
        return 0
    n = 0
    for m in TEXT_RUN_RE.finditer(s):
        text = m.group(1)
        # &amp; &lt; 등 엔티티는 단순히 한 글자 묶음으로 셈 (정확한 디코딩 필요 없음)
        n += len(text.strip())
    return n


def pick_richest(zsource: zipfile.ZipFile, pattern: re.Pattern) -> tuple[str, bytes] | None:
    """source zip 에서 pattern 매칭 파일 중 가장 텍스트 많은 항목.
    반환: (filename, bytes) 또는 None (후보 없음 또는 모두 빈 경우)."""
    candidates = []
    for n in zsource.namelist():
        if not pattern.match(n):
            continue
        data = zsource.read(n)
        chars = count_text_chars(data)
        if chars > 0:
            candidates.append((chars, n, data))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (-t[0], t[1]))  # 텍스트 많은 순, 동률 시 이름 순
    _, name, data = candidates[0]
    return name, data


def read_rels_for(zsource: zipfile.ZipFile, part_path: str) -> tuple[str, bytes] | None:
    """part_path 의 .rels 가 있으면 (rels_path, rels_bytes) 반환, 없으면 None."""
    folder = part_path.rsplit('/', 1)[0]
    name = part_path.rsplit('/', 1)[1]
    rels_path = f'{folder}/_rels/{name}.rels'
    if rels_path in zsource.namelist():
        return rels_path, zsource.read(rels_path)
    return None


def rewrite_rels_media_targets(rels_bytes: bytes, rename_map: dict[str, str]) -> bytes:
    """rels 의 Target 값 중 rename_map 에 있으면 새 값으로 치환.
    rename_map 키: 원래 Target (예: 'media/image2.png'), 값: 새 Target (예: 'media/hf_image2.png')."""
    s = rels_bytes.decode('utf-8', errors='replace')

    def repl(m):
        target = m.group(1)
        new = rename_map.get(target, target)
        return f'Target="{new}"'

    return RELS_TARGET_RE.sub(repl, s).encode('utf-8')


def strip_hdrftr_refs_from_sect(sect_xml: str) -> str:
    """sectPr 내 <w:headerReference .../> 및 <w:footerReference .../> 제거."""
    sect_xml = HDRREF_RE.sub('', sect_xml)
    sect_xml = FTRREF_RE.sub('', sect_xml)
    return sect_xml


def inject_hdrftr_refs(sect_xml: str, hdr_rid: str | None, ftr_rid: str | None) -> str:
    """비어 있지 않은 sectPr 내부 시작 부분에 default header/footer 참조 추가."""
    if not hdr_rid and not ftr_rid:
        return sect_xml
    inject = ''
    if hdr_rid:
        inject += f'<w:headerReference w:type="default" r:id="{hdr_rid}"/>'
    if ftr_rid:
        inject += f'<w:footerReference w:type="default" r:id="{ftr_rid}"/>'
    # 항상 <w:sectPr ...> 직후 (참조 요소들이 가장 먼저 와야 OOXML 스키마 준수)
    return re.sub(r'(<w:sectPr\b[^>]*>)', r'\1' + inject, sect_xml, count=1)


def patch_document_refs(doc_xml: str, hdr_rid: str | None, ftr_rid: str | None) -> tuple[str, int]:
    """document.xml 안 모든 sectPr 의 header/footer 참조를 새 것으로 교체.
    self-closing sectPr 는 건드리지 않음 (continuous 등).
    반환: (new_doc_xml, n_sects_patched)."""
    n = 0

    def repl(m):
        nonlocal n
        sect = m.group(0)
        sect = strip_hdrftr_refs_from_sect(sect)
        sect = inject_hdrftr_refs(sect, hdr_rid, ftr_rid)
        n += 1
        return sect

    return SECTPR_FULL_RE.sub(repl, doc_xml), n


def remove_hdrftr_ct_overrides(ct_xml: str) -> str:
    return CT_HDRFTR_OVERRIDE_RE.sub('', ct_xml)


def add_ct_override(ct_xml: str, part_name: str, content_type: str) -> str:
    """[Content_Types].xml 의 </Types> 직전에 Override 추가."""
    el = f'<Override PartName="{part_name}" ContentType="{content_type}"/>'
    return ct_xml.replace('</Types>', el + '</Types>', 1)


def remove_hdrftr_doc_relationships(docrels_xml: str) -> str:
    return DOCRELS_HDRFTR_REL_RE.sub('', docrels_xml)


def next_rid_from(docrels_xml: str, used_so_far: set[int]) -> int:
    """docrels 안 existing rId N 들 + 추가로 used_so_far 와 충돌하지 않는 다음 N."""
    used = set(int(m.group(1)) for m in DOCRELS_RID_RE.finditer(docrels_xml))
    used |= used_so_far
    n = max(used) + 1 if used else 1
    return n


def add_doc_relationship(docrels_xml: str, rid: str, rel_type: str, target: str) -> str:
    el = f'<Relationship Id="{rid}" Type="{rel_type}" Target="{target}"/>'
    return docrels_xml.replace('</Relationships>', el + '</Relationships>', 1)


def postprocess(input_path: Path, output_path: Path, source_path: Path, dry_run: bool = False) -> dict:
    """반환: {'status': ok|no-source|no-candidates, 'header': name|None, 'footer': name|None,
                'media': [renamed targets], 'sections_patched': N}"""
    if not source_path.exists():
        if input_path.resolve() != output_path.resolve():
            shutil.copyfile(str(input_path), str(output_path))
        return {'status': 'no-source', 'header': None, 'footer': None, 'media': [], 'sections_patched': 0}

    # 1) source 에서 텍스트 많은 header/footer 선정 + 그들 rels + media 모두 수집
    with zipfile.ZipFile(source_path) as zsrc:
        hdr_pick = pick_richest(zsrc, HEADER_FN_RE)
        ftr_pick = pick_richest(zsrc, FOOTER_FN_RE)

        collected = {
            'header_xml': None,   # (new_name, bytes)
            'header_rels': None,  # (new_rels_name, bytes)
            'footer_xml': None,
            'footer_rels': None,
            'media': {},          # new_path -> bytes (예: 'word/media/hf_image5.jpeg' -> bytes)
            'media_renames': {},  # original 'media/x' -> new 'media/hf_x' (.rels 안의 Target 키)
        }

        # 새 part 이름은 단순화: 항상 headerSync.xml / footerSync.xml.
        # 출력 docx 안 기존 header/footer 는 모두 지우므로 충돌 가능성 없음.
        if hdr_pick is not None:
            _, hdr_bytes = hdr_pick
            collected['header_xml'] = ('word/headerSync.xml', hdr_bytes)
        if ftr_pick is not None:
            _, ftr_bytes = ftr_pick
            collected['footer_xml'] = ('word/footerSync.xml', ftr_bytes)

        if hdr_pick is None and ftr_pick is None:
            if input_path.resolve() != output_path.resolve():
                shutil.copyfile(str(input_path), str(output_path))
            return {'status': 'no-candidates', 'header': None, 'footer': None, 'media': [], 'sections_patched': 0}

        # rels + media 수집
        for kind, pick in (('header', hdr_pick), ('footer', ftr_pick)):
            if pick is None:
                continue
            src_name, _ = pick
            rels_info = read_rels_for(zsrc, src_name)
            if rels_info is None:
                continue
            rels_path, rels_bytes = rels_info
            # 이 rels 안의 media Target 들 수집 + 'hf_' 접두 이름매핑
            rels_str = rels_bytes.decode('utf-8', errors='replace')
            local_renames = {}
            for m in RELS_TARGET_RE.finditer(rels_str):
                target = m.group(1)
                if not target.startswith('media/'):
                    continue
                # source 의 실제 미디어 경로 = word/<target>
                src_media_path = f'word/{target}'
                if src_media_path not in zsrc.namelist():
                    continue
                media_data = zsrc.read(src_media_path)
                # 새 이름: word/media/hf_<basename>
                basename = target.split('/', 1)[1]  # 'image5.jpeg'
                new_basename = f'hf_{basename}'
                new_target = f'media/{new_basename}'
                new_path = f'word/{new_target}'
                local_renames[target] = new_target
                collected['media'][new_path] = media_data
                collected['media_renames'][target] = new_target
            # rels 안 Target 재작성
            new_rels = rewrite_rels_media_targets(rels_bytes, local_renames)
            if kind == 'header':
                collected['header_rels'] = ('word/_rels/headerSync.xml.rels', new_rels)
            else:
                collected['footer_rels'] = ('word/_rels/footerSync.xml.rels', new_rels)

    if dry_run:
        return {
            'status': 'ok-dryrun',
            'header': hdr_pick[0] if hdr_pick else None,
            'footer': ftr_pick[0] if ftr_pick else None,
            'media': sorted(collected['media'].keys()),
            'sections_patched': 0,
        }

    # 2) output zip 재작성
    with zipfile.ZipFile(input_path) as zin:
        names = zin.namelist()
        contents = {n: zin.read(n) for n in names}

    # 2a) 기존 header/footer 및 rels 제거
    to_delete = [
        n for n in list(contents.keys())
        if HEADER_FN_RE.match(n) or FOOTER_FN_RE.match(n)
        or HEADER_RELS_RE.match(n) or FOOTER_RELS_RE.match(n)
    ]
    for n in to_delete:
        del contents[n]

    # 2b) [Content_Types].xml — 기존 header/footer Override 제거 + 새것 추가
    ct = contents['[Content_Types].xml'].decode('utf-8')
    ct = remove_hdrftr_ct_overrides(ct)
    if collected['header_xml']:
        ct = add_ct_override(ct, '/' + collected['header_xml'][0], HDR_CT)
    if collected['footer_xml']:
        ct = add_ct_override(ct, '/' + collected['footer_xml'][0], FTR_CT)
    contents['[Content_Types].xml'] = ct.encode('utf-8')

    # 2c) document.xml.rels — 기존 header/footer Relationship 제거 + 새 rId 할당해 추가
    docrels = contents['word/_rels/document.xml.rels'].decode('utf-8')
    docrels = remove_hdrftr_doc_relationships(docrels)
    used_rids = set()
    new_hdr_rid = None
    new_ftr_rid = None
    if collected['header_xml']:
        n = next_rid_from(docrels, used_rids); used_rids.add(n)
        new_hdr_rid = f'rId{n}'
        # Target 은 word/_rels/document.xml.rels 기준 상대 — word/headerSync.xml -> headerSync.xml
        target = collected['header_xml'][0].split('/', 1)[1]
        docrels = add_doc_relationship(docrels, new_hdr_rid, HDR_REL_TYPE, target)
    if collected['footer_xml']:
        n = next_rid_from(docrels, used_rids); used_rids.add(n)
        new_ftr_rid = f'rId{n}'
        target = collected['footer_xml'][0].split('/', 1)[1]
        docrels = add_doc_relationship(docrels, new_ftr_rid, FTR_REL_TYPE, target)
    contents['word/_rels/document.xml.rels'] = docrels.encode('utf-8')

    # 2d) document.xml — sectPr 안 참조 교체
    doc_xml = contents['word/document.xml'].decode('utf-8')
    new_doc, n_sects = patch_document_refs(doc_xml, new_hdr_rid, new_ftr_rid)
    contents['word/document.xml'] = new_doc.encode('utf-8')

    # 2e) 새 header/footer XML + rels + media 추가
    for key in ('header_xml', 'header_rels', 'footer_xml', 'footer_rels'):
        if collected[key] is not None:
            name, data = collected[key]
            contents[name] = data
    for path, data in collected['media'].items():
        # 기존 동일 경로 미디어가 있으면 (충돌) 그대로 둠 — 'hf_' 접두 덕분에 사실상 발생 안 함
        contents[path] = data

    # 3) zip 출력 — 원래 순서 유지 + 새 항목은 뒤에 추가
    final_order = [n for n in names if n in contents]
    final_order.extend(n for n in contents.keys() if n not in final_order)
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zout:
        for n in final_order:
            zout.writestr(n, contents[n])

    return {
        'status': 'ok',
        'header': hdr_pick[0] if hdr_pick else None,
        'footer': ftr_pick[0] if ftr_pick else None,
        'media': sorted(collected['media'].keys()),
        'sections_patched': n_sects,
    }


def main():
    ap = argparse.ArgumentParser(
        description="output docx 의 머리글/바닥글을 사용자 양식 docx 의 텍스트 있는 한 쌍으로 교체"
    )
    ap.add_argument('docx', help='대상 output docx (in-place 또는 --out 지정)')
    ap.add_argument('--source', required=True, help='머리글/바닥글 소스 docx (사용자 양식 원본)')
    ap.add_argument('--out', help='별도 출력 경로 (기본: in-place)')
    ap.add_argument('--dry-run', action='store_true', help='추출 후보만 보고')
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

    source = Path(args.source)
    if not source.exists():
        print(f"ERROR: source not found: {source}", file=sys.stderr)
        return 1

    if args.dry_run:
        info = postprocess(inp, inp, source, dry_run=True)
        if info['status'] == 'no-candidates':
            print(f"[POSTPROCESS-HF-DRY] {source.name} 에 텍스트 있는 header/footer 없음")
        else:
            print(f"[POSTPROCESS-HF-DRY] header={info['header']}  footer={info['footer']}")
            print(f"[POSTPROCESS-HF-DRY] media (재명명 후): {info['media']}")
        return 0

    out = Path(args.out) if args.out else inp

    if out.resolve() == inp.resolve():
        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            info = postprocess(inp, tmp_path, source)
            shutil.move(str(tmp_path), str(inp))
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        loc = 'in-place'
    else:
        info = postprocess(inp, out, source)
        loc = str(out.name)

    if info['status'] == 'ok':
        h = info['header'] or '(없음)'
        f = info['footer'] or '(없음)'
        media_n = len(info['media'])
        print(f"[POSTPROCESS-HF] header={h} footer={f} media={media_n}개 sectPr={info['sections_patched']}개 ({loc})")
    elif info['status'] == 'no-source':
        print(f"[POSTPROCESS-HF] --source 없음 — 건너뜀 ({loc})")
    elif info['status'] == 'no-candidates':
        print(f"[POSTPROCESS-HF] source 에 텍스트 있는 header/footer 없음 — 건너뜀 ({loc})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
