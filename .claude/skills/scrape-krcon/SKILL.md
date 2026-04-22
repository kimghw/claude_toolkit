---
name: scrape-krcon
description: "KR-CON (한국선급 IMO 협약 원문 DB, https://krcon.krs.co.kr) 문서 스크래핑. SOLAS, MARPOL, COLREG 등 협약 문서를 수집하거나, krcon_documents.json 갱신, 누락 ID 재수집, 트리 구조 재탐색이 필요할 때 사용. '크라콘 스크래핑', 'krcon 수집', 'IMO 협약 문서 수집' 요청에 대응."
when_to_use: "krcon 스크래핑, krcon 수집, KR-CON 재수집, 누락 문서 수집, 세션 만료 후 재실행, SOLAS/MARPOL/COLREG 수집"
allowed-tools: "Bash Read Write Edit Grep Glob"
---

# KR-CON 스크래핑 스킬

한국선급 IMO 협약 원문 DB(`https://krcon.krs.co.kr`)에서 문서를 수집한다.

## 0. 프로젝트 위치

- **스크립트**: `${CLAUDE_SKILL_DIR}/scripts/` (스킬 내 자체 복제본)
- **데이터 출력**: `/home/kimghw/krcon_data/` (JSON 파일 — 스크립트 내 `OUTPUT_DIR`로 하드코딩됨)
- **가이드 원문**: [KRCON_SCRAPING_GUIDE.md](KRCON_SCRAPING_GUIDE.md) — 사이트 구조·엔드포인트·필드 상세

> 스크립트 내부의 `OUTPUT_DIR`은 절대경로이므로, 스킬 내부 복제본을 실행해도 결과 JSON은 동일한 `/home/kimghw/krcon_data/` 위치에 저장된다. 원본 `/home/kimghw/krcon_data/scripts/`의 스크립트와는 독립된 사본이므로, 수정 시 어느 쪽을 고칠지 명확히 할 것.

## 1. 작업 흐름

다음 순서로 진행한다.

### Step 1 — 세션 쿠키 확인
```bash
ls -la /home/kimghw/krcon_data/session_cookies.json
```
- 파일 존재 + 최근 수정 시각이 **24시간 이내**면 재사용 가능
- 없거나 오래됐으면 Step 2로

### Step 2 — 세션 유효성 검사
다음 curl로 세션이 살아있는지 확인한다(쿠키 파일을 로드하는 간단한 Python 1-liner 권장):
```bash
cd /home/kimghw/krcon_data && python3 -c "
import json, requests
c = json.load(open('session_cookies.json'))
r = requests.get('https://krcon.krs.co.kr/Functions/TreeView/List.aspx?LocaleKey=en&Tree=0000.00e0', cookies=c, timeout=10)
print('EXPIRED' if ('Log In' in r.text and len(r.text) < 5000) else f'OK ({len(r.text)} bytes)')
"
```
- `EXPIRED` → 사용자에게 로그인 필요 알림, `scrape_full.py` 실행 시 대화형으로 ID/PW 입력받음
- `OK` → 기존 쿠키로 계속 진행

### Step 3 — 수집 방법 선택
사용자 요청에 맞춰 방법을 고른다.

| 요청 유형 | 스크립트 | 설명 |
|---|---|---|
| 전체 수집 / 갱신 (1차) | `scrape_full.py` | 트리 BFS + View.aspx, 중간 저장, 재개 지원, 세션 만료 시 대화형 로그인 |
| 누락 ID 보충 (2차) | `scrape_all_remaining.py` | 1~78438 중 미수집 ID만 병렬 스캔 |
| 결과 분할 (후처리) | `split_documents.py` | 대용량 JSON을 20MB/파일 단위로 분할 |

> 보통 `scrape_full.py` → `scrape_all_remaining.py` 순으로 실행한다. 특정 협약(SOLAS 등) 집중 수집이 필요하면 `scrape_full.py`의 `tree_queue`를 해당 트리 코드만 남기도록 수정해서 실행.

### Step 4 — 실행
```bash
cd /home/kimghw/krcon_data && python3 ${CLAUDE_SKILL_DIR}/scripts/<chosen_script>.py
```
- `cd`는 필수 — 스크립트가 `session_cookies.json` 등을 상대경로로 읽음
- 장시간(수십 분~수 시간) 걸리므로 **`run_in_background: true`로 실행**하고 주기적으로 출력 확인
- 진행 로그는 50건 단위로 표시, 200건 단위로 중간 저장됨

### Step 5 — 결과 확인
```bash
ls -lh /home/kimghw/krcon_data/*.json
python3 -c "import json; d=json.load(open('/home/kimghw/krcon_data/krcon_documents.json')); print(f'총 {len(d)}개, 본문있음 {sum(1 for x in d if x.get(\"content_html\"))}개, 오류 {sum(1 for x in d if x.get(\"error\"))}개')"
```

## 2. 핵심 엔드포인트 (직접 요청이 필요할 때)

- **목록**: `GET /Functions/TreeView/List.aspx?LocaleKey=en&Tree={tree_code}`
- **문서**: `GET /Functions/TreeView/View.aspx?Tab=TreeView&LocaleKey=en&Id={doc_id}`
- **트리 코드 예**: `0000.00e0`(루트) / `.1530`(SOLAS) / `.04b0`(MARPOL) / `.06tp`(COLREG)
- **필수 쿠키 3종**: `.AUTHCOOKIE`, `ASP.NET_SessionId`, `KRCON`

## 3. 추출 필드 (View.aspx HTML)

| HTML | 필드 |
|---|---|
| `hfCategoryTitle` hidden | `full_path` (예: `SOLAS / Chapter I / Reg. 1`) |
| `lblContent` span | `content_html`, `content_text` |
| `lblHeader` span | `header` (JS 섞임 — 정리 필요) |
| `ddlnextamend` / `ddlpreviousamend` | 개정 문서 ID 연결 |

## 4. 주의사항

1. **병렬도는 10스레드 이하**로 유지 — 초과 시 서버 응답 지연/차단 위험
2. **요청 간격**: 문서당 0.2s 권장, 빈 ID 탐색은 0.05s 가능
3. **세션 만료 감지**: 응답에 "Log In" + 5000자 미만이면 만료
4. **중간 저장**은 `.tmp → os.replace`로 원자적이므로 중단 안전
5. **재실행 시** 기존 `krcon_documents.json`을 읽어 `content_html` 없는 건만 다시 수집함
6. **트리 3단계+ 탐색 불가**: Telerik 서버 세션 제한 → Selenium 기반 접근이 필요 (현재 스킬에는 미포함, 원본 `/home/kimghw/krcon_data/scripts/scrape_krcon.py` 참고)
7. **파일 크기**: 전체 수집 시 수백 MB → 필요 시 `split_documents.py`로 20MB/파일 분할

## 5. 세션 만료 시 로그인 절차

`scrape_full.py`는 세션 만료 감지 시 대화형으로 KRCON ID/PW를 입력받아 로그인한다. 다음을 먼저 사용자에게 확인:

- KRCON 계정 보유 여부 (유료 서비스)
- 장시간 수집이면 백그라운드 실행(`run_in_background: true`) + 주기 확인 전략 합의
- 결과 파일 위치(`/home/kimghw/krcon_data/krcon_documents.json`) 확인

로그인 성공 시 `session_cookies.json`에 쿠키가 저장되어 다음 실행부터 재사용된다.

## 6. 사용자에게 먼저 물어볼 것

작업 시작 전 다음을 확인한다.

1. **어떤 범위?** — 전체 갱신 / 특정 협약(SOLAS 등) / 누락만
2. **이어서 할지 처음부터?** — 기본은 이어서(기존 `krcon_documents.json` 유지)
3. **백그라운드 실행 여부** — 긴 작업이면 권장
