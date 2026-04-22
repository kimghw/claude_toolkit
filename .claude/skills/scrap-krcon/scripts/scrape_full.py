#!/usr/bin/env python3
"""
KR-CON 전체 문서 스크래퍼
- ID/PW로 로그인
- 트리 구조 탐색하여 모든 문서 ID 수집
- 각 문서의 메타데이터 + 본문 수집
- JSON으로 저장 (중간 저장 포함)
"""

import requests
import re
import json
import time
import sys
import os
from html.parser import HTMLParser
from html import unescape
from getpass import getpass

BASE = "https://krcon.krs.co.kr"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
OUTPUT_DIR = "/home/kimghw/krcon_data"


# ─── HTML Parsers ───────────────────────────────────────────────

class TableParser(HTMLParser):
    """List.aspx 테이블에서 행 추출"""
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.in_link = False
        self.current_row = []
        self.current_href = ""
        self.rows = []  # [(path, title, href), ...]

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'table' and 'rgMasterTable' in attrs_dict.get('class', ''):
            self.in_table = True
        if self.in_table:
            if tag == 'tr':
                self.in_row = True
                self.current_row = []
                self.current_href = ""
            if tag in ('td', 'th'):
                self.in_cell = True
                self.current_row.append('')
            if tag == 'a' and self.in_cell:
                href = attrs_dict.get('href', '')
                if 'View.aspx' in href:
                    self.current_href = href
                self.in_link = True

    def handle_endtag(self, tag):
        if self.in_table:
            if tag in ('td', 'th'):
                self.in_cell = False
            if tag == 'a':
                self.in_link = False
            if tag == 'tr':
                self.in_row = False
                if self.current_row and self.current_row != ['PATH', 'TITLE']:
                    path = self.current_row[0] if len(self.current_row) > 0 else ''
                    title = self.current_row[1] if len(self.current_row) > 1 else ''
                    self.rows.append((path, title, self.current_href))
            if tag == 'table' and self.in_table:
                self.in_table = False

    def handle_data(self, data):
        if self.in_cell and self.current_row:
            self.current_row[-1] += data.strip()


def extract_doc_id(href):
    """URL에서 문서 ID 추출"""
    m = re.search(r'Id=(\d+)', href)
    return m.group(1) if m else None


def extract_hidden_fields(html):
    """ASP.NET hidden fields 추출"""
    fields = {}
    for fid in ['__VIEWSTATE', '__EVENTVALIDATION', '__REAL_VIEWSTATE',
                 'ctl00_BodyContentPlaceHolder_RadScriptManager1_TSM',
                 '__REAL_StatePersister']:
        m = re.search(rf'name="{fid}"[^>]*value="([^"]*)"', html)
        if not m:
            m = re.search(rf'id="{fid}"[^>]*value="([^"]*)"', html)
        if m:
            fields[fid] = m.group(1)
    return fields


def extract_tree_links(html):
    """HTML에서 트리 경로 링크 추출"""
    trees = set()
    for m in re.finditer(r'List\.aspx[^"]*?Tree=([0-9a-z.]+)', html, re.IGNORECASE):
        trees.add(m.group(1))
    for m in re.finditer(r'View\.aspx[^"]*?IsViewChild=True[^"]*?Tree=([0-9a-z.]+)', html, re.IGNORECASE):
        trees.add(m.group(1))
    return trees


def extract_doc_ids_from_html(html):
    """HTML에서 모든 문서 ID 추출"""
    return set(re.findall(r'View\.aspx[^"]*?Id=(\d+)', html))


def strip_tags(html_str):
    """HTML 태그 제거하여 텍스트만 추출"""
    text = re.sub(r'<[^>]+>', '', html_str)
    text = unescape(text)
    # 연속 공백/줄바꿈 정리
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def parse_view_page(html):
    """View.aspx에서 문서 메타데이터 + 본문 추출"""
    doc = {}

    # 카테고리 제목 (경로 포함)
    m = re.search(r'hfCategoryTitle[^>]*value="([^"]*)"', html)
    if m:
        full_title = unescape(m.group(1))
        doc['full_path'] = full_title
        # 마지막 / 뒤가 실제 제목
        parts = full_title.rsplit(' / ', 1)
        doc['title'] = parts[-1] if parts else full_title
        if len(parts) > 1:
            doc['category_path'] = parts[0]

    # 본문 HTML
    m = re.search(r'lblContent">([\s\S]*?)</span>\s*</div>', html)
    if not m:
        m = re.search(r'lblContent">([\s\S]*?)</span>', html)
    if m:
        doc['content_html'] = m.group(1).strip()
        doc['content_text'] = strip_tags(m.group(1))

    # lblHeader에서 추가 정보
    m = re.search(r'lblHeader"[^>]*>([\s\S]*?)</(?:span|div)', html)
    if m:
        header_text = strip_tags(m.group(1))
        if header_text and 'header' not in doc:
            doc['header'] = header_text

    # 모든 hidden field (hf*) 자동 수집
    for m in re.finditer(r'name="([^"]*)"[^>]*value="([^"]*)"', html):
        name = m.group(1)
        val = m.group(2).strip()
        if not val:
            continue
        # 큰 ASP.NET 시스템 필드 제외
        if any(skip in name for skip in ['VIEWSTATE', 'EVENTVALIDATION',
                                          'TSM', 'StatePersister', 'hdnScreen',
                                          'hdnNewMemoCnt']):
            continue
        # ctl00$...$ prefix 제거
        short = re.sub(r'^ctl00\$\w+\$', '', name)
        short = re.sub(r'^hf', '', short)
        short = short.lower()
        if short and short not in doc:
            doc[short] = unescape(val)

    return doc


# ─── Login ──────────────────────────────────────────────────────

def login(session, user_id, password):
    """KRCON 로그인"""
    print("로그인 페이지 접속...", flush=True)
    resp = session.get(f"{BASE}/Authentication/Login.aspx",
                       headers={"User-Agent": UA})
    fields = extract_hidden_fields(resp.text)

    post_data = {
        'ctl00_RadScriptManager1_TSM': fields.get('ctl00_BodyContentPlaceHolder_RadScriptManager1_TSM', ''),
        '__REAL_StatePersister': fields.get('__REAL_StatePersister', 'RCL.Core.CachePageStatePersister'),
        '__REAL_VIEWSTATE': fields.get('__REAL_VIEWSTATE', ''),
        '__VIEWSTATE': fields.get('__VIEWSTATE', ''),
        '__EVENTVALIDATION': fields.get('__EVENTVALIDATION', ''),
        '__EVENTTARGET': 'ctl00$BodyContentPlaceHolder$btnLogin',
        '__EVENTARGUMENT': '',
        'ctl00$BodyContentPlaceHolder$hdnScreenWidth': '1920',
        'ctl00$BodyContentPlaceHolder$hdnScreenHeight': '1080',
        'ctl00$BodyContentPlaceHolder$txtId': user_id,
        'ctl00$BodyContentPlaceHolder$txtPwd': password,
    }

    print("로그인 시도...", flush=True)
    resp = session.post(f"{BASE}/Authentication/Login.aspx",
                        data=post_data,
                        headers={"User-Agent": UA,
                                 "Content-Type": "application/x-www-form-urlencoded",
                                 "Referer": f"{BASE}/Authentication/Login.aspx"},
                        allow_redirects=True)

    # 로그인 성공 확인
    if '.AUTHCOOKIE' in {c.name for c in session.cookies}:
        print("로그인 성공!", flush=True)
        return True

    # 쿠키 이름이 다를 수 있으니 실제 페이지 접근으로 확인
    test = session.get(f"{BASE}/Functions/TreeView/List.aspx?LocaleKey=en&Tree=0000.00e0",
                       headers={"User-Agent": UA})
    if 'Log In' in test.text and 'Password' in test.text and len(test.text) < 5000:
        print("로그인 실패!", flush=True)
        return False

    print("로그인 성공! (페이지 접근 확인)", flush=True)
    return True


# ─── Phase 1: 트리 탐색 + 문서 ID 수집 ──────────────────────────

def collect_doc_ids(session):
    """트리 구조를 BFS 탐색하며 모든 문서 ID 수집"""
    print("\n=== Phase 1: 트리 탐색 + 문서 ID 수집 ===", flush=True)

    # 초기 트리 경로 (루트 + 주요 카테고리)
    tree_queue = [
        "0000.00e0", "0000.00e0.1530", "0000.00e0.04b0", "0000.00e0.10c1",
        "0000.00e0.1110", "0000.00e0.10z0", "0000.00e0.1569", "0000.00e0.06tp",
        "0000.00e0.1540", "0000.00e0.1210", "0000.00e0.1230", "0000.00e0.1240",
        "0000.00e0.1160", "0000.00e0.05g0", "0000.00e0.1170", "0000.00e0.1565",
        "0000.00e0.1563", "0000.00e0.1480", "0000.00e0.1310", "0000.00e0.1571",
        "0000.00e0.1570", "0000.00e0.1567", "0000.00e0.1180", "0000.00e0.1190",
        "0000.00e0.1260", "0000.00e0.1561", "0000.00e0.1290", "0000.00e0.1564",
        "0000.00e0.1560", "0000.00e0.1566", "0000.00e0.1562", "0000.00e0.1120",
        "0000.00e0.05r0", "0000.00e0.10c0", "0000.00e0.1150", "0000.00e0.1320",
        "0000.00e0.02m0", "0000.00e0.03i0", "0000.00e0.1340", ".0000",
    ]
    visited_trees = set()
    all_doc_ids = set()
    list_info = {}  # doc_id -> {path, title} from list page

    idx = 0
    while idx < len(tree_queue):
        tree = tree_queue[idx]
        idx += 1

        if tree in visited_trees:
            continue
        visited_trees.add(tree)

        try:
            url = f"{BASE}/Functions/TreeView/List.aspx?LocaleKey=en&Tree={tree}"
            resp = session.get(url, headers={"User-Agent": UA}, timeout=15)
            html = resp.text

            if 'Log In' in html and 'Password' in html and len(html) < 5000:
                print(f"\n세션 만료! (트리 {tree})", flush=True)
                return all_doc_ids, list_info

            # 이 목록 페이지에서 문서 ID 추출
            page_ids = extract_doc_ids_from_html(html)
            all_doc_ids.update(page_ids)

            # 테이블 파싱 → 목록 정보 저장
            parser = TableParser()
            parser.feed(html)
            for path, title, href in parser.rows:
                doc_id = extract_doc_id(href)
                if doc_id:
                    list_info[doc_id] = {'path': path, 'title': title}

            # 하위 트리 링크 수집
            sub_trees = extract_tree_links(html)
            for st in sub_trees:
                if st not in visited_trees and st not in tree_queue:
                    tree_queue.append(st)

            # 페이지네이션: 목록이 여러 페이지일 수 있음
            fields = extract_hidden_fields(html)
            page_num = 2
            empty_count = 0
            while empty_count < 3:
                event_target = f"ctl00$BodyContentPlaceHolder$RealPager1$numberButton{page_num}"
                post_data = {
                    'ctl00_BodyContentPlaceHolder_RadScriptManager1_TSM': fields.get('ctl00_BodyContentPlaceHolder_RadScriptManager1_TSM', ''),
                    '__REAL_StatePersister': fields.get('__REAL_StatePersister', 'RCL.Core.CachePageStatePersister'),
                    '__REAL_VIEWSTATE': fields.get('__REAL_VIEWSTATE', ''),
                    '__VIEWSTATE': fields.get('__VIEWSTATE', ''),
                    '__EVENTTARGET': event_target,
                    '__EVENTARGUMENT': '',
                    '__EVENTVALIDATION': fields.get('__EVENTVALIDATION', ''),
                    'ctl00$BodyContentPlaceHolder$txtTitle': '',
                }
                try:
                    resp2 = session.post(url, data=post_data, headers={
                        "User-Agent": UA,
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Referer": url,
                    }, timeout=15)
                    html2 = resp2.text

                    page_ids2 = extract_doc_ids_from_html(html2)
                    if not page_ids2:
                        empty_count += 1
                        page_num += 1
                        continue

                    empty_count = 0
                    new_ids = page_ids2 - all_doc_ids
                    if not new_ids:
                        # 같은 페이지 반복 → 중단
                        break

                    all_doc_ids.update(page_ids2)

                    parser2 = TableParser()
                    parser2.feed(html2)
                    for path, title, href in parser2.rows:
                        doc_id = extract_doc_id(href)
                        if doc_id:
                            list_info[doc_id] = {'path': path, 'title': title}

                    fields = extract_hidden_fields(html2)
                    page_num += 1
                    time.sleep(0.1)

                except Exception:
                    break

        except Exception as e:
            print(f"  오류 ({tree}): {e}", flush=True)

        if idx % 10 == 0:
            print(f"  트리: {idx}/{len(tree_queue)} 탐색, "
                  f"{len(all_doc_ids)}개 문서 발견", flush=True)
        time.sleep(0.15)

    print(f"\n트리 탐색 완료: {len(visited_trees)}개 경로, "
          f"{len(all_doc_ids)}개 문서", flush=True)
    return all_doc_ids, list_info


# ─── Phase 2: 각 문서 상세 수집 ─────────────────────────────────

def collect_documents(session, doc_ids, list_info):
    """각 문서의 View.aspx에서 메타데이터 + 본문 수집"""
    ids = sorted(doc_ids, key=int)
    total = len(ids)
    print(f"\n=== Phase 2: {total}개 문서 상세 수집 ===", flush=True)

    output_file = os.path.join(OUTPUT_DIR, "krcon_documents.json")

    # 이미 수집된 데이터가 있으면 이어서
    existing = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                for doc in json.load(f):
                    if doc.get('id'):
                        existing[str(doc['id'])] = doc
            print(f"  기존 데이터 {len(existing)}개 로드 (이어서 수집)", flush=True)
        except Exception:
            pass

    results = []
    skipped = 0
    errors = 0

    for i, doc_id in enumerate(ids):
        # 이미 수집된 건 건너뜀
        if doc_id in existing and existing[doc_id].get('content_html'):
            results.append(existing[doc_id])
            skipped += 1
            continue

        try:
            url = (f"{BASE}/Functions/TreeView/View.aspx?"
                   f"Tab=TreeView&LocaleKey=en&Id={doc_id}&Search=")
            resp = session.get(url, headers={"User-Agent": UA}, timeout=15)
            html = resp.text

            if 'Log In' in html and 'Password' in html and len(html) < 5000:
                print(f"\n세션 만료! (문서 {doc_id}, {i+1}/{total})", flush=True)
                print("수집된 데이터까지 저장합니다.", flush=True)
                break

            doc = parse_view_page(html)
            doc['id'] = doc_id

            # List 페이지에서 가져온 정보 보충
            if doc_id in list_info:
                if 'path' not in doc or not doc.get('category_path'):
                    doc['category_path'] = list_info[doc_id]['path']
                if 'title' not in doc or not doc['title']:
                    doc['title'] = list_info[doc_id]['title']

            results.append(doc)

        except Exception as e:
            errors += 1
            results.append({
                'id': doc_id,
                'error': str(e),
                'title': list_info.get(doc_id, {}).get('title', ''),
                'category_path': list_info.get(doc_id, {}).get('path', ''),
            })

        # 진행상황 + 중간저장
        done = i + 1
        if done % 50 == 0:
            pct = done / total * 100
            print(f"  [{done}/{total}] {pct:.1f}% "
                  f"(건너뜀:{skipped}, 오류:{errors})", flush=True)

        if done % 200 == 0:
            save_json(results, output_file)
            print(f"  중간 저장 ({len(results)}개)", flush=True)

        time.sleep(0.2)

    save_json(results, output_file)
    print(f"\n=== 수집 완료 ===", flush=True)
    print(f"  총 문서: {len(results)}개", flush=True)
    print(f"  건너뜀 (기존): {skipped}개", flush=True)
    print(f"  오류: {errors}개", flush=True)
    print(f"  저장: {output_file}", flush=True)
    return results


def save_json(data, filepath):
    """JSON 저장 (임시 파일 → rename으로 안전하게)"""
    tmp = filepath + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, filepath)


# ─── Main ───────────────────────────────────────────────────────

def create_session_with_cookies():
    """쿠키 파일 또는 하드코딩된 쿠키로 세션 생성"""
    session = requests.Session()
    session.headers.update({"User-Agent": UA})

    # 쿠키 파일이 있으면 로드
    cookies_file = os.path.join(OUTPUT_DIR, "session_cookies.json")
    if os.path.exists(cookies_file):
        with open(cookies_file, 'r') as f:
            cookies = json.load(f)
        session.cookies.update(cookies)
        print(f"쿠키 파일 로드: {cookies_file}", flush=True)
    else:
        session.cookies.update({
            '.AUTHCOOKIE': '091CD7F88B7218B03F5945D2D417C39C7E782F5F7383D4885A4B7015D5EE80FDF17953B000D39B815D50B3E3073380288AEC1D3F1CE69DAB97B45EBFEDFA1119445E1479A3E248CBD2E0691192740CDF957B4E18EB990CB5B72FDCDC96468DE31183E049B7C0508D7A396C78B4F51D8948AA815B5E6A410C20B2CC519B777CD2D8F15DCC',
            'ASP.NET_SessionId': 'ua5xw245sfwkceesf2f4bm45',
            'KRCON': 'H4sIAL9FyGkA/+2V72/SQBjHQZRo1VcmxhhjmL82BzagTlxSNLNsphkDAsw3C8Fr+6ycXO/weoXhK/8+/x7fzzvmMnolwh/gQzjoPZ/ePf0+T5/LZDOZzLk09avszjU5WIcdu9UsFb4AjzCjtYpZVp9SwY6JiDnUKMSCI1IqtGOXYO8QZj02AlqjMSE31FKF+QqmTTBQ0XK/gSci8zgC7vhyAovZhoTuWw2YAPkwGgw+IW+EaXCAgfj3LGeszz2wbBZTwWe6o2DtEcKmRzIw3GABpuk7nWjPD9OOx9LRnUUCwqXuh5ZDKXAVs+56ZO2fjTkGv44E6M4tqw08xJESrofcHgfY97FgqVU2k6A9BG/UwJHQuZdJzgmZLbcNWFqLV9qKjE6U2PKC+ShFl5N0VyARR63Tq7tWBGIzH44QRUFaoO0keTz2ZcRNJrCXkmsjiR6g7zrxIknU2ZQShnwde649TuyGKJ1VbTtZMTrxRIt9Sf61iJpwJtocJjpWXKZCWwJSshXJ6MApcKCeFFgAx4hE/ywzWWM2BySQS2AVOA9jHbAOBJaCm53p5VtclK9lOEZ0popB50qLXIsHiOIfSBXWMvjZIqxEXwtqojAFPV2E5i3BSRdLkvEQAdnDUsWySPWGkN4rk73smwnL5XLZC7uphrvZpP3MXvQd02aEyM4oJYnMzyC7DfZMR/WAr5WTk79MV3C5W6kQRh7jBLtXXfn1ul3ZrVbRjrfzrrL75i2U3+/2+/8j6PfVQZeXX8NQKTv/WP0db/0qapk0DCOfm//JX1en44h7jA5GOAyG01tqZj4Yxu0/riaoEkkHAAA=',
        })

    # 세션 유효 확인
    print("세션 확인 중...", flush=True)
    resp = session.get(f"{BASE}/Functions/TreeView/List.aspx?LocaleKey=en&Tree=0000.00e0",
                       headers={"User-Agent": UA}, timeout=10)
    if 'Log In' in resp.text and 'Password' in resp.text and len(resp.text) < 5000:
        print("세션 만료! 로그인이 필요합니다.", flush=True)
        user_id = input("KRCON ID: ").strip()
        password = getpass("KRCON PW: ")
        if not login(session, user_id, password):
            print("로그인 실패.")
            sys.exit(1)
        save_json(dict(session.cookies), cookies_file)
    else:
        print("세션 유효!", flush=True)

    return session


def main():
    print("=" * 60)
    print("  KR-CON 전체 문서 스크래퍼")
    print("=" * 60)

    session = create_session_with_cookies()

    # Phase 1: 트리 탐색
    doc_ids, list_info = collect_doc_ids(session)

    # ID 목록 저장
    ids_file = os.path.join(OUTPUT_DIR, "krcon_doc_ids.json")
    save_json({
        "total": len(doc_ids),
        "ids": sorted(doc_ids, key=int),
        "list_info": list_info,
    }, ids_file)
    print(f"문서 ID 저장: {ids_file} ({len(doc_ids)}개)", flush=True)

    # Phase 2: 문서 상세 수집
    results = collect_documents(session, doc_ids, list_info)

    # 최종 통계
    print(f"\n{'=' * 60}")
    has_content = sum(1 for r in results if r.get('content_html'))
    has_title = sum(1 for r in results if r.get('title'))
    has_error = sum(1 for r in results if r.get('error'))
    print(f"  전체: {len(results)}개")
    print(f"  제목 있음: {has_title}개")
    print(f"  본문 있음: {has_content}개")
    print(f"  오류: {has_error}개")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
