#!/usr/bin/env python3
"""
krcon_documents.json을 카테고리별로 분할하고,
단일 파일이 너무 크면 추가로 청크 분할.

출력 구조:
  krcon_data/
    documents/
      index.json          - 전체 문서 목록 (id, title, category, 파일 위치)
      {category_slug}/
        part_001.json     - 문서 데이터 (최대 MAX_FILE_MB)
        part_002.json
        ...
"""

import json
import os
import re
import sys

INPUT = "/home/kimghw/krcon_data/krcon_documents.json"
OUTPUT_DIR = "/home/kimghw/krcon_data/documents"
MAX_FILE_MB = 20  # 단일 파일 최대 크기 (MB)
MAX_DOCS_PER_FILE = 200  # 파일당 최대 문서 수


def slugify(text):
    """카테고리명을 파일명에 안전한 형태로 변환"""
    text = text.strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s]+', '_', text)
    text = text.strip('_')
    return text[:80] or 'uncategorized'


def get_category(doc):
    """문서에서 최상위 카테고리 추출"""
    path = doc.get('category_path') or doc.get('full_path') or ''
    if ' / ' in path:
        return path.split(' / ')[0].strip()
    return path.strip() or 'uncategorized'


def main():
    print(f"입력 파일: {INPUT}")
    file_size_mb = os.path.getsize(INPUT) / (1024 * 1024)
    print(f"파일 크기: {file_size_mb:.1f} MB")

    with open(INPUT, 'r', encoding='utf-8') as f:
        docs = json.load(f)
    print(f"총 문서: {len(docs)}개")

    # 카테고리별 분류
    by_category = {}
    for doc in docs:
        cat = get_category(doc)
        by_category.setdefault(cat, []).append(doc)

    print(f"카테고리: {len(by_category)}개")
    for cat, cat_docs in sorted(by_category.items(), key=lambda x: -len(x[1])):
        print(f"  {cat}: {len(cat_docs)}개")

    # 출력 디렉토리 생성
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    index = []
    total_files = 0

    for cat, cat_docs in sorted(by_category.items()):
        cat_slug = slugify(cat)
        cat_dir = os.path.join(OUTPUT_DIR, cat_slug)
        os.makedirs(cat_dir, exist_ok=True)

        # 청크 분할
        chunks = []
        current_chunk = []
        for doc in cat_docs:
            current_chunk.append(doc)
            if len(current_chunk) >= MAX_DOCS_PER_FILE:
                chunks.append(current_chunk)
                current_chunk = []
        if current_chunk:
            chunks.append(current_chunk)

        # 각 청크 저장
        for ci, chunk in enumerate(chunks):
            filename = f"part_{ci+1:03d}.json"
            filepath = os.path.join(cat_dir, filename)
            rel_path = os.path.relpath(filepath, OUTPUT_DIR)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(chunk, f, ensure_ascii=False, indent=2)

            file_size = os.path.getsize(filepath) / (1024 * 1024)
            total_files += 1

            # 파일이 너무 크면 더 작게 분할
            if file_size > MAX_FILE_MB:
                os.remove(filepath)
                total_files -= 1
                sub_size = max(10, len(chunk) // int(file_size / MAX_FILE_MB + 1))
                for si in range(0, len(chunk), sub_size):
                    sub_chunk = chunk[si:si+sub_size]
                    sub_filename = f"part_{ci+1:03d}_{si//sub_size+1:02d}.json"
                    sub_filepath = os.path.join(cat_dir, sub_filename)
                    sub_rel = os.path.relpath(sub_filepath, OUTPUT_DIR)

                    with open(sub_filepath, 'w', encoding='utf-8') as f:
                        json.dump(sub_chunk, f, ensure_ascii=False, indent=2)
                    total_files += 1

                    for doc in sub_chunk:
                        index.append({
                            'id': doc.get('id'),
                            'title': doc.get('title', ''),
                            'category': cat,
                            'file': sub_rel,
                        })
            else:
                for doc in chunk:
                    index.append({
                        'id': doc.get('id'),
                        'title': doc.get('title', ''),
                        'category': cat,
                        'file': rel_path,
                    })

    # 인덱스 저장
    index_path = os.path.join(OUTPUT_DIR, "index.json")
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump({
            'total_documents': len(docs),
            'total_files': total_files,
            'categories': {cat: len(cat_docs) for cat, cat_docs in sorted(by_category.items())},
            'documents': index,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n=== 분할 완료 ===")
    print(f"  출력 디렉토리: {OUTPUT_DIR}")
    print(f"  파일 수: {total_files}개")
    print(f"  인덱스: {index_path}")

    # 파일 크기 확인
    total_size = 0
    for root, dirs, files in os.walk(OUTPUT_DIR):
        for fn in files:
            fp = os.path.join(root, fn)
            size = os.path.getsize(fp) / (1024 * 1024)
            total_size += size
            if size > MAX_FILE_MB:
                print(f"  경고: {fp} = {size:.1f}MB (초과)")
    print(f"  총 크기: {total_size:.1f} MB")


if __name__ == '__main__':
    main()
