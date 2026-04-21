---
description: "claude_toolkit 웹서버(web_service/server.py) 실행. FastAPI/uvicorn 기반 127.0.0.1:8765. 포트 충돌 시 대체 포트 안내."
argument-hint: "[port] | stop | status"
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion
---

<!-- markdownlint-disable -->

# /web 명령 — claude_toolkit 웹서버 실행

인자: $ARGUMENTS

## 경로 정의

- `$CLAUDE_TOOLKIT_ROOT` — `claude_toolkit` 레포 루트. 아래 **탐지** 절차로 매번 결정한다. 본 문서에서는 편의상 `$TOOLKIT`으로도 표기.
- `$WEB = $CLAUDE_TOOLKIT_ROOT/web_service` — 실행 디렉토리. `server.py`, `requirements.txt` 존재 확인.
- **`CLAUDE_TOOLKIT_ROOT` 식별자** (고정 상수, 하드코딩):
  ```
  CLAUDE_TOOLKIT_ROOT_ID=5a7a5dc046eda268d64df3af621de2c1640f0d66b0abe71fc2509f5e9562b319
  ```
  이 값은 `$CLAUDE_TOOLKIT_ROOT/.project_id` 파일에 기록돼 있으며, 해당 파일의 내용이 이 ID와 일치하고 그 바로 아래 `web_service/server.py` 가 있는 디렉토리만 유효한 `$CLAUDE_TOOLKIT_ROOT`로 인정한다.

## 탐지 (모든 동작에 선행, 매번 실행)

각 단계에서 후보가 나오면 **반드시 `<후보>/web_service/server.py` 존재까지** 확인한 뒤 확정한다. 파일이 없으면 그 후보는 기각하고 다음 단계로 내려간다 (`web_service/` 는 `claude_toolkit` 루트에만 존재).

1. **환경변수 빠른 경로** — `$CLAUDE_TOOLKIT_ROOT`가 설정되어 있으면:
   - `grep -q "$CLAUDE_TOOLKIT_ROOT_ID" "$CLAUDE_TOOLKIT_ROOT/.project_id" 2>/dev/null` 로 ID 매칭 확인.
   - `test -f "$CLAUDE_TOOLKIT_ROOT/web_service/server.py"` 로 server.py 존재 확인.
   - 둘 다 통과 → 그대로 사용하고 탐색 스킵.
   - 하나라도 실패 → `"CLAUDE_TOOLKIT_ROOT이 유효하지 않음 — 재탐색합니다"` 고지 후 다음 단계로 폴백.

2. **현재 프로젝트 자체가 toolkit인지 확인** — `$CLAUDE_PROJECT_DIR/.project_id` 의 ID 매칭 + `$CLAUDE_PROJECT_DIR/web_service/server.py` 존재 둘 다 통과하면 `CLAUDE_TOOLKIT_ROOT="$CLAUDE_PROJECT_DIR"`로 확정.

3. **파일명 기반 탐색 (느린 경로)**:
   - 탐색 루트 후보(존재하는 것만, 중복 제거):
     - `/mnt/c /mnt/d /mnt/e` (Windows 드라이브 마운트)
     - `$HOME`, `/home`
     - `$CLAUDE_PROJECT_DIR/..`, `$CLAUDE_PROJECT_DIR/../..` (상위 2단)
   - 잡음 폴더는 `prune`로 제외:
     ```
     find <roots> \( -name node_modules -o -name .git -o -name .venv \
         -o -name dist -o -name build \) -prune \
         -o -type f -name '.project_id' -print 2>/dev/null
     ```
   - 후보 각각에 대해 `grep -l "$CLAUDE_TOOLKIT_ROOT_ID" <file>` 로 ID 매칭 여부 확인.
   - ID 매칭된 후보의 부모 디렉토리에 **`web_service/server.py` 가 있는 것만** 최종 후보로 남긴다.

4. **매칭 개수별 분기**:
   - **정확히 1개**: 그 파일의 부모 디렉토리를 `$CLAUDE_TOOLKIT_ROOT`으로 확정.
   - **2개 이상**: `AskUserQuestion`으로 사용자에게 선택을 묻는다. 각 후보를 `<경로>` 형식으로 제시. 후보가 4개를 넘으면 상위 3개 + `그 외 직접 입력` 옵션으로 구성.
   - **0개**: 에러 고지 후 `AskUserQuestion`(자유 텍스트 입력)으로 `$CLAUDE_TOOLKIT_ROOT` 경로 직접 지정 요청. 입력받은 경로는 `.project_id` ID 일치 + `web_service/server.py` 존재 둘 다 통과해야 수용, 불일치면 재질의.

5. **확정 후 사후 처리**:
   - 보고: `CLAUDE_TOOLKIT_ROOT = <경로>`.
   - `$CLAUDE_TOOLKIT_ROOT` 환경변수가 미설정이거나 확정 경로와 다르면, 쉘 rc에 다음을 추가하도록 **안내만** 한다(자동 수정 금지):
     ```
     export CLAUDE_TOOLKIT_ROOT="<확정 경로>"
     ```

## 인자

| 인자 | 동작 |
|------|------|
| (없음) | 기본 포트 `8765`로 **포어그라운드 실행**. |
| `<숫자>` (예: `9000`) | 해당 포트로 실행. |
| `bg` 또는 `background` | 백그라운드 실행 (로그는 `$WEB/.server.log`). |
| `stop` | 실행 중인 서버 프로세스를 찾아 종료. |
| `status` | 현재 실행 상태 · PID · 포트 조회. |

> `bg` 와 포트 지정을 병용하려면 `/web bg 9000` 처럼 두 인자 사용.

## 동작 순서

### 공통 사전 점검

1. `$WEB/server.py` 존재 확인 — 없으면 에러 후 중단.
2. `python3 --version` 확인 (3.10+ 권장). 없으면 설치 안내 후 중단.
3. venv 준비 및 의존성 설치 (기본 동작):

   ```bash
   # venv 없으면 생성
   [ -d "$WEB/.venv" ] || python3 -m venv "$WEB/.venv"
   # venv의 python/pip 를 사용
   PY="$WEB/.venv/bin/python"
   "$PY" -c "import fastapi, uvicorn" 2>/dev/null \
     || "$PY" -m pip install -r "$WEB/requirements.txt"
   ```

   - `$WEB/.venv` 는 **항상 `web_service/` 아래**에 둔다. 루트 `.gitignore` 의 `.venv*/` 규칙으로 자동 무시됨.
   - `python3-venv` 패키지가 없어 `python -m venv` 실패 시 `sudo apt-get install -y python3-venv` 안내.
   - 시스템 파이썬에 직접 설치하고 싶다는 환경변수(`CLAUDE_TOOLKIT_NO_VENV=1`)가 있을 때만 `pip install --user -r "$WEB/requirements.txt"` 로 폴백.

### 1. 기본 실행 (인자 없음 또는 포트 지정)

1. 포트 결정: 인자로 숫자가 오면 그 포트, 아니면 `8765`.
2. 포트 점유 여부 점검:

   ```bash
   (ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null) | grep -E ":${PORT}\\b"
   ```

   - 점유 중이면 `lsof -iTCP:${PORT} -sTCP:LISTEN` 로 프로세스 확인 후 사용자에게 선택: **중단 / 다른 포트로 재시도 / 기존 프로세스 종료**.
3. 포어그라운드 실행 (venv python 사용):

   ```bash
   cd "$WEB" && "$WEB/.venv/bin/python" -m uvicorn server:app --host 127.0.0.1 --port "$PORT"
   ```

   `CLAUDE_TOOLKIT_NO_VENV=1` 폴백 모드에서는 `python3 -m uvicorn ...` 사용.

4. 시작 직후 5초 내 `curl -sf http://127.0.0.1:${PORT}/` 로 핸드셰이크 확인. 응답 없으면 로그 표시.
5. 사용자 Ctrl+C 로 종료.

### 2. 백그라운드 실행 (`bg` / `background`)

1. PID 파일 점검: `$WEB/.server.pid` 가 있고 해당 PID 가 살아 있으면 "이미 실행 중" 보고 후 `status` 동작으로 분기.
2. nohup + `run_in_background` 로 기동 (venv python 사용):

   ```bash
   cd "$WEB" && nohup "$WEB/.venv/bin/python" -m uvicorn server:app --host 127.0.0.1 --port "$PORT" \
     > "$WEB/.server.log" 2>&1 &
   echo $! > "$WEB/.server.pid"
   ```

3. 3초 대기 후 `/` 핑 확인. 성공 시 PID·포트·로그 경로 보고.

### 3. `stop`

1. `$WEB/.server.pid` 읽어 해당 PID 에 `kill` 시도. 5초 내 미종료면 `kill -9`.
2. PID 파일 제거.
3. PID 파일이 없으면 `pgrep -f "uvicorn.*server:app"` 로 폴백 탐색 후 사용자 확인 후 종료.

### 4. `status`

1. `$WEB/.server.pid` 존재 여부 → PID 살아 있는지 → 리스닝 포트 → 최근 로그 tail 10줄.
2. 표 형식으로 보고.

## 동작 규칙

- **호스트는 기본 `127.0.0.1`**. 외부 노출이 필요하면 사용자가 명시적으로 `HOST=0.0.0.0 /web` 식으로 환경변수 지정. 보안상 기본 바인드는 루프백 유지.
- **포트 자동 변경 금지**: 점유 시 사용자에게 물어본 뒤 변경. 무음 변경은 혼란 유발.
- **의존성은 `$WEB/.venv` 의 venv 기반 기본 설치**. 시스템 파이썬 오염 방지. `CLAUDE_TOOLKIT_NO_VENV=1` 일 때만 `pip install --user` 폴백.
- **포어그라운드 실행이 기본**. 에이전트 흐름에서 블로킹을 피하려면 명시적으로 `bg` 사용.

## 예시

- `/web` → 127.0.0.1:8765 포어그라운드 실행.
- `/web 9000` → 127.0.0.1:9000 포어그라운드 실행.
- `/web bg` → 백그라운드 실행 (기본 포트).
- `/web bg 9000` → 백그라운드, 포트 9000.
- `/web status` → 현재 상태 조회.
- `/web stop` → 실행 중이면 종료.
