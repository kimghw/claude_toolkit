#!/usr/bin/env python3
"""전체 미수집 ID 병렬 수집 — SOLAS 이후 나머지 전부"""

import requests, re, json, time, os
from html import unescape
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

BASE = "https://krcon.krs.co.kr"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
OUTPUT_DIR = "/home/kimghw/krcon_data"
WORKERS = 10

COOKIES = {
    '.AUTHCOOKIE': '043407AC8D0B588508C06595F4AC70530CB7EBE7F365C1FB342D391D23EC39AD6FB43F6DF214C853DEE11736A0B5C63F7B75932B8D58870B589AF5B91D36CEE4EBFF9295326CB14DB7A85E82E724F782E9C0A3022DEF61816914A36B664454A7A5C723406FADE9AAD5F99D82B8F7C3150342F521ED5D455FB4A88E85466D3A429E703145',
    'ASP.NET_SessionId': 'ckne2p45mjfqmc55tef22s2w',
    'KRCON': 'H4sIAOTpyGkA/+2V72/SQBjHQZRo1VcmxhhjmL82BzagTlxSNLNsphkDAsw3C8Fr+6ycXO/weoXhK/8+/x7fzzvmMnolwh/gQzjoPZ/ePf0+T5/LZDOZzLk09avszjU5WIcdu9UsFb4AjzCjtYpZVp9SwY6JiDnUKMSCI1IqtGOXYO8QZj02AlqjMSE31FKF+QqmTTBQ0XK/gSci8zgC7vhyAovZhoTuWw2YAPkwGgw+IW+EaXCAgfj3LGeszz2wbBZTwWe6o2DtEcKmRzIw3GABpuk7nWjPD9OOx9LRnUUCwqXuh5ZDKXAVs+56ZO2fjTkGv44E6M4tqw08xJESrofcHgfY97FgqVU2k6A9BG/UwJHQuZdJzgmZLbcNWFqLV9qKjE6U2PKC+ShFl5N0VyARR63Tq7tWBGIzH44QRUFaoO0keTz2ZcRNJrCXkmsjiR6g7zrxIknU2ZQShnwde649TuyGKJ1VbTtZMTrxRIt9Sf61iJpwJtocJjpWXKZCWwJSshXJ6MApcKCeFFgAx4hE/ywzWWM2BySQS2AVOA9jHbAOBJaCm53p5VtclK9lOEZ0popB50qLXIsHiOIfSBXWMvjZIqxEXwtqojAFPV2E5i3BSRdLkvEQAdnDUsWySPWGkN4rk73smwnL5XLZC7uphrvZpP3MXvQd02aEyM4oJYnMzyC7DfZMR/WAr5WTk79MV3C5W6kQRh7jBLtXXfn1ul3ZrVbRjrfzrrL75i2U3+/2+/8j6PfVQZeXX8NQKTv/WP0db/0qapk0DCOfm//JX1en44h7jA5GOAyG01tqZj4Yxu0/riaoEkkHAAA=',
}

lock = threading.Lock()
stats = {'checked': 0, 'found': 0, 'errors': 0, 'expired': False}


def strip_tags(s):
    s = re.sub(r'<[^>]+>', '', s)
    s = unescape(s)
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()


def parse_view(html):
    doc = {}
    m = re.search(r'hfCategoryTitle[^>]*value="([^"]*)"', html)
    if m:
        ft = unescape(m.group(1))
        doc['full_path'] = ft
        parts = ft.rsplit(' / ', 1)
        doc['title'] = parts[-1] if parts else ft
        if len(parts) > 1:
            doc['category_path'] = parts[0]
    m = re.search(r'lblContent">([\s\S]*?)</span>\s*</div>', html)
    if not m:
        m = re.search(r'lblContent">([\s\S]*?)</span>', html)
    if m:
        doc['content_html'] = m.group(1).strip()
        doc['content_text'] = strip_tags(m.group(1))
    for m2 in re.finditer(r'name="([^"]*)"[^>]*value="([^"]*)"', html):
        name, val = m2.group(1), m2.group(2).strip()
        if not val or any(x in name for x in ['VIEWSTATE','EVENTVALIDATION','TSM','StatePersister','hdnScreen','hdnNewMemoCnt']):
            continue
        short = re.sub(r'^ctl00\$\w+\$', '', name)
        short = re.sub(r'^hf', '', short).lower()
        if short and short not in doc:
            doc[short] = unescape(val)
    return doc


def is_valid(html):
    return len(html) > 500 and 'hfCategoryTitle' in html


def fetch(doc_id, session):
    if stats['expired']:
        return None
    try:
        r = session.get(f"{BASE}/Functions/TreeView/View.aspx?Tab=TreeView&LocaleKey=en&Id={doc_id}&Search=",
                        timeout=10)
        if 'Log In' in r.text and 'Password' in r.text and len(r.text) < 5000:
            stats['expired'] = True
            return None
        with lock:
            stats['checked'] += 1
        if is_valid(r.text):
            doc = parse_view(r.text)
            doc['id'] = str(doc_id)
            with lock:
                stats['found'] += 1
            return doc
        return None
    except:
        with lock:
            stats['checked'] += 1
            stats['errors'] += 1
        return None


def save_json(data, path):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def main():
    print("=" * 50, flush=True)
    print(f"  전체 미수집 ID 병렬 수집 ({WORKERS} threads)", flush=True)
    print("=" * 50, flush=True)

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    session.cookies.update(COOKIES)

    # 모든 기존 수집 ID 로드
    all_known_ids = set()

    main_file = os.path.join(OUTPUT_DIR, "krcon_documents.json")
    with open(main_file, 'r', encoding='utf-8') as f:
        main_docs = json.load(f)
    all_known_ids.update(int(d['id']) for d in main_docs if d.get('id'))

    for extra_name in ['krcon_solas_extra.json', 'krcon_documents_extra.json']:
        fp = os.path.join(OUTPUT_DIR, extra_name)
        if os.path.exists(fp):
            with open(fp, 'r', encoding='utf-8') as f:
                edocs = json.load(f)
            all_known_ids.update(int(d['id']) for d in edocs if d.get('id'))

    max_id = max(all_known_ids)
    print(f"기존 수집: {len(all_known_ids)}개 (max ID: {max_id})", flush=True)

    # 전체 범위에서 미수집 ID
    missing = sorted(set(range(1, max_id + 1)) - all_known_ids)
    total = len(missing)
    print(f"미수집 ID: {total}개", flush=True)

    # 세션 확인
    r = session.get(f"{BASE}/Functions/TreeView/View.aspx?Tab=TreeView&LocaleKey=en&Id={min(all_known_ids)}&Search=", timeout=15)
    if not is_valid(r.text):
        print("세션 만료!", flush=True)
        return
    print("세션 OK!", flush=True)

    # 수집
    output_file = os.path.join(OUTPUT_DIR, "krcon_all_extra.json")
    new_docs = []
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            new_docs = json.load(f)
        already = {int(d['id']) for d in new_docs if d.get('id')}
        missing = [i for i in missing if i not in already]
        total = len(missing)
        print(f"이어서: 기존 extra {len(new_docs)}개, 남은 {total}개", flush=True)

    start = time.time()

    for batch_start in range(0, total, 500):
        if stats['expired']:
            break
        batch = missing[batch_start:batch_start + 500]

        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            futures = {ex.submit(fetch, did, session): did for did in batch}
            for f in as_completed(futures):
                doc = f.result()
                if doc:
                    new_docs.append(doc)
                if stats['expired']:
                    break

        elapsed = time.time() - start
        rate = stats['checked'] / elapsed if elapsed > 0 else 0
        remaining = (total - stats['checked']) / rate / 60 if rate > 0 else 0
        print(f"  [{stats['checked']}/{total}] 발견:{stats['found']} "
              f"오류:{stats['errors']} 속도:{rate:.0f}/초 남은:{remaining:.1f}분", flush=True)

        save_json(new_docs, output_file)

    # 최종 병합
    save_json(new_docs, output_file)

    # 전체 병합: main + solas_extra + all_extra → 중복 제거
    all_docs = {}
    for d in main_docs:
        if d.get('id'):
            all_docs[str(d['id'])] = d

    for extra_name in ['krcon_solas_extra.json', 'krcon_all_extra.json', 'krcon_documents_extra.json']:
        fp = os.path.join(OUTPUT_DIR, extra_name)
        if os.path.exists(fp):
            with open(fp, 'r', encoding='utf-8') as f:
                for d in json.load(f):
                    if d.get('id') and str(d['id']) not in all_docs:
                        all_docs[str(d['id'])] = d

    merged = list(all_docs.values())
    save_json(merged, main_file)

    # 분할
    print("\n문서 분할 중...", flush=True)
    os.system(f"python3 {os.path.join(OUTPUT_DIR, 'split_documents.py')}")

    elapsed = time.time() - start
    print(f"\n{'=' * 50}", flush=True)
    print(f"  확인: {stats['checked']}개", flush=True)
    print(f"  신규: {stats['found']}개", flush=True)
    print(f"  전체 문서: {len(merged)}개", flush=True)
    print(f"  시간: {elapsed/60:.1f}분", flush=True)
    print(f"{'=' * 50}", flush=True)


if __name__ == '__main__':
    main()
