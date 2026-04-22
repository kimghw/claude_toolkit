# KR-CON 데이터 수집 가이드

## 1. KR-CON 사이트 개요

- **URL**: https://krcon.krs.co.kr
- **운영**: 한국선급(KRS, Korean Register of Shipping)
- **내용**: IMO 국제해사협약 원문 데이터베이스 (SOLAS, MARPOL, COLREG 등)
- **인증**: 로그인 필수 (유료 서비스)

---

## 2. 인증 방식

### 로그인
- **URL**: `https://krcon.krs.co.kr/` (메인페이지에서 로그인 모달)
- **방식**: AJAX POST → `/Generators/ProcessLogin.aspx`
- **파라미터**:
  - `UID`: base64 인코딩된 사용자 ID
  - `PWD`: base64 인코딩된 비밀번호
  - `CATE`: `"LOGIN"`
  - `ScreenWidth`, `ScreenHeight`
- **응답**: JSON `{"Result":"Success","Msg":"..."}` 또는 `{"Result":"ErrorMsg","Msg":"..."}`

### 필수 쿠키 (3개)
| 쿠키명 | 설명 |
|--------|------|
| `.AUTHCOOKIE` | 인증 토큰 (hex 문자열, ~260자) |
| `ASP.NET_SessionId` | ASP.NET 세션 ID |
| `KRCON` | 사용자 설정 (gzip+base64, ~700자) |

> 세션 만료 시 `View.aspx` 응답에 "Log In" 텍스트 + 짧은 HTML(< 5000자)이 반환됨

### 쿠키 확인 방법
브라우저에서 KRCON 로그인 후 F12 → Console:
```javascript
document.cookie
```

---

## 3. 사이트 구조

### 프레임 구조
```
krcon.krs.co.kr/
├── Index/MainBody.aspx          ← 메인 화면 (대시보드)
├── Functions/TreeView/
│   ├── Left.aspx                ← 좌측 트리 메뉴 (Telerik RadTreeView)
│   ├── List.aspx?Tree=xxx       ← 카테고리 문서 목록 (테이블)
│   └── View.aspx?Id=xxx         ← 개별 문서 조회
└── Generators/
    └── ProcessLogin.aspx        ← 로그인 API
```

### 트리뷰 (Left.aspx)
- **기술**: Telerik RadTreeView (ASP.NET WebForms)
- **노드 확장**: `ServerSideCallBack` 방식
- **콜백 방식**:
  - `__CALLBACKID`: RadTreeView 컨트롤 UniqueID
  - `__CALLBACKPARAM`: `{"Command":"NodeExpand","Index":"0:0"}`
  - Index 형식: `부모:자식` (예: `0:0` = 루트의 첫번째 자식)
- **제한**: 2단계까지만 콜백 가능 (서버 세션 상태 문제로 3단계+ 불가)

### 트리 코드 체계
```
0000.00e0              → KR-CON (English) 루트
0000.00e0.1530         → SOLAS ***
0000.00e0.1530.0740    → SOLAS Consolidated Edition
0000.00e0.1530.1848    → SOLAS Amendments
0000.00e0.04b0         → MARPOL ***
0000.00e0.06tp         → COLREG ***
...
```

---

## 4. 주요 엔드포인트

### List.aspx — 문서 목록
```
GET /Functions/TreeView/List.aspx?LocaleKey=en&Tree=0000.00e0.1530
```
- 해당 트리 하위의 문서 목록 (테이블)
- 페이지네이션: ASP.NET PostBack (`__EVENTTARGET=ctl00$...RealPager1$numberButton{n}`)
- 응답: HTML 테이블 (rgMasterTable 클래스)

### View.aspx — 문서 조회
```
GET /Functions/TreeView/View.aspx?Tab=TreeView&LocaleKey=en&Id={doc_id}&Search=
```
- 개별 문서의 메타데이터 + 본문
- **주요 필드**:

| HTML 요소 | 내용 |
|-----------|------|
| `hfCategoryTitle` (hidden) | 전체 경로 (예: `SOLAS / Chapter I / Reg. 1`) |
| `lblContent` (span) | 본문 HTML |
| `lblHeader` (span) | 헤더 정보 |
| `hfCategoryPath` (hidden) | 카테고리 경로 |
| `nextpreviouscontrol$ddlnextamend` | 다음 개정 문서 ID |
| `nextpreviouscontrol$ddlpreviousamend` | 이전 개정 문서 ID |

### View.aspx?IsViewChild=True — 하위 문서 뷰
```
GET /Functions/TreeView/View.aspx?LocaleKey=en&IsViewChild=True&Tree=0000.00e0.1530
```
- 해당 트리의 하위 문서를 보여주는 뷰 (트리 확장 시 사용)

---

## 5. 데이터 수집 방법

### 방법 1: 트리 탐색 (List.aspx)
1. `Left.aspx`에서 1~2단계 트리 노드 확장 (콜백)
2. 각 트리 코드로 `List.aspx?Tree=xxx` 접근
3. 테이블에서 문서 ID 추출 (`View.aspx?Id=xxx` 링크)
4. 페이지네이션으로 모든 페이지 순회

**장점**: 구조화된 수집, 카테고리 정보 확보
**단점**: 3단계+ 트리 접근 불가, 페이지네이션 복잡

### 방법 2: ID 브루트포스 (View.aspx)
1. 문서 ID 범위(1~78438) 전체를 순회
2. 각 ID로 `View.aspx?Id=xxx` 접근
3. 유효한 문서만 수집 (hfCategoryTitle 존재 여부로 판별)

**장점**: 모든 문서 수집 가능, 트리 구조 무관
**단점**: 빈 ID가 많아 시간 소요 (전체 ~78,000개 중 유효 문서 ~50,000개 추정)

### 방법 3: 병렬 ID 스캔 (권장)
- 방법 2를 `concurrent.futures.ThreadPoolExecutor`로 병렬화
- 10 스레드 기준 약 3 ID/초 처리
- 유효 문서 히트율: 약 60~80% (구간에 따라 다름)

---

## 6. 수집 데이터 필드

| 필드 | 출처 | 설명 |
|------|------|------|
| `id` | URL 파라미터 | 문서 고유 ID (정수) |
| `full_path` | hfCategoryTitle | 전체 카테고리 경로 (예: `SOLAS / Chapter I / Reg. 1`) |
| `title` | full_path에서 추출 | 문서 제목 (경로의 마지막 부분) |
| `category_path` | full_path에서 추출 | 상위 카테고리 경로 |
| `content_html` | lblContent | 본문 HTML 원문 |
| `content_text` | content_html 변환 | 본문 텍스트 (태그 제거) |
| `categorytitle` | hfCategoryTitle | 전체 경로 (full_path과 동일) |
| `header` | lblHeader | 헤더 (JS 코드 섞임 — 정리 필요) |

---

## 7. 파일 구조

```
krcon_data/
├── KRCON_SCRAPING_GUIDE.md          ← 이 문서
│
├── 수집 데이터
│   ├── krcon_documents.json         ← 메인 문서 (5,038개, 113MB)
│   ├── krcon_solas_extra.json       ← SOLAS 구간 추가 수집
│   ├── krcon_all_extra.json         ← 전체 구간 추가 수집
│   ├── krcon_documents_extra.json   ← 초기 브루트포스 추가 수집
│   └── documents/                   ← 카테고리별 분할 (20MB/200개 단위)
│       ├── index.json               ← 인덱스
│       └── {category}/part_NNN.json
│
├── 트리 구조
│   ├── full_tree.json               ← 전체 2단계 트리 (203개 노드)
│   ├── tree_structure.json          ← 1단계 트리 코드 매핑
│   └── solas_tree.json              ← SOLAS 트리 상세
│
├── 기타
│   ├── krcon_list.csv               ← 초기 목록 (중복 많음, 참고용)
│   ├── krcon_doc_ids.json           ← 트리 탐색으로 발견한 ID 목록
│   └── session_cookies.json         ← 마지막 세션 쿠키
│
└── 스크립트
    ├── scrape_full.py               ← 1차 수집 (트리 탐색 + View.aspx)
    ├── scrape_solas_v2.py           ← SOLAS 구간 병렬 수집
    ├── scrape_all_remaining.py      ← 전체 미수집 ID 병렬 수집
    ├── scrape_all.py                ← 초기 목록 수집 (List.aspx 페이지네이션)
    ├── scrape_deep.py               ← 깊은 트리 탐색 시도
    ├── scrape_missing.py            ← 누락 ID 수집 (단일 스레드)
    ├── scrape_solas.py              ← SOLAS 수집 v1
    ├── scrape_krcon.py              ← Selenium 기반 수집
    ├── scrape_v2.py                 ← Selenium v2
    └── split_documents.py           ← 문서 분할 스크립트
```

---

## 8. 트리 구조 (1~2단계)

```
KR-CON (English) [0000.00e0]
├── SOLAS ***                   [.1530]  → Consolidated Edition, Amendments
├── MARPOL ***                  [.04b0]  → Consolidated Edition, Amendments
├── AFS Convention              [.10c1]
├── Bunker Convention           [.1110]  → Articles, Annex, Appendix (leaf)
├── BWM Convention ***          [.10z0]
├── BWMS Code                   [.1569]
├── COLREG ***                  [.06tp]
├── ESP Code ***                [.1540]
├── FSS Code ***                [.1210]
├── FTP Code ***                [.1230]
├── HSC Code ***                [.1240]  → 2000, 1994, DSC
├── IBC Code ***                [.1160]
├── ICLL Convention ***         [.05g0]  → 1966 Convention, 1988 Protocol
├── IGC Code ***                [.1170]
├── IGF Code ***                [.1565]
├── III Code                    [.1563]  → Part 1~4
├── IMDG Code***                [.1480]  → 2010~2024 각 버전 (10개)
├── IMSBC Code ***              [.1310]
├── INF Code***                 [.1571]
├── IP Code ***                 [.1570]
├── IS Code ***                 [.1567]
├── ISM Code ***                [.1180]
├── ISPS Code ***               [.1190]
├── LSA Code ***                [.1260]
├── MLC Convention ***          [.1561]
├── MODU Code ***               [.1290]  → 2009, 1989, 1979
├── Noise Code                  [.1564]  → Chapter 1~7, Appendix 1~4
├── NOx Code ***                [.1560]
├── POLAR Code ***              [.1566]
├── RO Code ***                 [.1562]
├── Hong Kong Ship Recycling    [.1120]
├── STCW Conv & Codes ***       [.05r0]  → STCW, Manila 2010, STCW-F
├── Tonnage Convention          [.10c0]  → Articles, Annex 1~3, Appendix
├── more CONVENTIONs            [.1150]  → 25개 (Athens, CLC, CSC, FUND...)
├── more CODEs                  [.1320]  → 15개 (BC, BCH, BLU, CSS, GC...)
├── RESOLUTIONs                 [.02m0]  → Assembly, MSC, MEPC, FAL, LEG, SOLAS Conf
├── CIRCULARs                   [.03i0]  → MSC, MEPC, MSC-MEPC 등 18개
├── IACS                        [.1340]  → UI, Recommendations
├── PSC PROCEDURES              (NodeKind=Link, ID=27154)
├── HSSC SURVEY GUIDELINES      (NodeKind=Link, ID=39306)
├── COW SYSTEM                  (NodeKind=Link, ID=33031)
├── SOPEP                       (NodeKind=Link, ID=33050)
├── CAS                         (NodeKind=Link, ID=36988)
└── TESTING OF LSA              (NodeKind=Link, ID=49559)
```

---

## 9. 주의사항

1. **세션 만료**: 쿠키는 일정 시간 후 만료됨 (정확한 시간 미확인, 수시간~1일)
2. **서버 부하**: 병렬 10스레드 이상은 서버 응답 지연 발생
3. **요청 간격**: 문서당 0.2초 대기 권장 (빈 ID는 0.05초도 가능)
4. **Telerik 제한**: Left.aspx 트리 3단계+ 확장은 requests로 불가 (Selenium 필요)
5. **header 필드**: JavaScript 코드가 섞여 있어 정리 필요
6. **content_html**: HTML 원문이므로 텍스트 추출 시 태그 제거 필요
7. **파일 크기**: 전체 수집 시 수백 MB — 분할 저장 권장 (20MB/파일)
8. **ID 체계**: 문서 ID는 1~78438 범위, 비연속적 (유효 문서 ~50,000개 추정)

---

## 10. 수집 이력

| 일시 | 작업 | 결과 |
|------|------|------|
| 2026-03-28 | 1차 트리 탐색 + 수집 | 5,038개 문서 (40개 트리) |
| 2026-03-29 | SOLAS 구간 ID 브루트포스 | ~5,000개 추가 (진행중) |
| 2026-03-29 | 전체 구간 ID 브루트포스 | ~65,000개 확인 예정 (진행중) |
| 2026-03-29 | 전체 트리 구조 확보 | 203개 노드 (2단계) |
