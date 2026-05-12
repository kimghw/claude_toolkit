---
name: port_manager
description: 현재 프로젝트의 서버·포트를 SSOT(port_list.md)에서 조회·등록·갱신·삭제하고, 등록된 서버를 상태확인→종료→재시작까지 처리. 행이 0이면 등록 안내, 1이면 자동 재시작, 2+이면 AskUserQuestion으로 선택받아 재시작. 포트 검색·종료·기동·표 편집은 port_ops.sh 스크립트로 위임. TRIGGER when 사용자가 /port_manager 호출, 현재 프로젝트 포트·서버 등록·조회·재시작·재기동 요청. DO NOT TRIGGER when 외부 호스트 접속, 배포·CI 파이프라인.
allowed-tools: Bash AskUserQuestion Read
argument-hint: [show|all|add|<port>|rm <port>|help]
---

# port_manager — 프로젝트 서버 등록·조회·재시작

본 스킬은 **현재 프로젝트의 서버 정의(port_list.md)**를 관리하고, 등록된 서버를 **"상태 확인 → 실행 중이면 종료 → 새로 기동"** 시킨다. 인자에 따라 조회/등록/삭제 모드로도 동작한다.

> 본 스킬은 부작용(프로세스 kill·서버 기동·SSOT 파일 편집)을 일으킨다. 결과 검증은 호출 시점 Claude의 책임이다.

## 핵심 원칙

- **단일 출처(SSOT)**: 모든 결정은 `port_list.md` 한 파일에서 시작한다. 다른 곳을 추측하지 않는다.
- **스크립트 우선**: 포트 검색·상태·종료·기동·표 편집은 모두 `port_ops.sh` 가 처리한다. Claude가 `ss`/`lsof`/`kill`/`awk`/`sed` 로 표를 직접 다루지 않는다.
- **현재 프로젝트만**: `basename "$CLAUDE_PROJECT_DIR"` 으로 결정한 프로젝트만 다룬다. 다른 프로젝트 행은 `all` 모드에서만 표시한다.
- **수량으로 분기**: 재시작 모드에서 행 수가 0 → 안내, 1 → 자동, 2+ → `AskUserQuestion` 으로 선택.
- **재시작은 명시적 절차**: `status → kill(있을 때만) → start → status` 순서를 따른다.

## 인자 분기 (`$ARGUMENTS`)

| 인자 | 모드 | 동작 |
|:---|:---|:---|
| (없음) | **재시작** | 현재 프로젝트 행을 보여주고 1행이면 자동 재시작, 2+행이면 `AskUserQuestion` 선택 후 재시작. 0행이면 등록 안내. |
| `show` | **조회** | 현재 프로젝트 행을 출력만. 재시작 안 함. 0행이면 미등록 메시지. |
| `all` 또는 `list` | **전체 조회** | `port_list.md` 전체 표를 그대로 출력. 다른 프로젝트 포함. |
| `<숫자>` | **등록/갱신** | 그 포트로 등록(미존재) 또는 갱신(존재). 서비스·시작명령·작업디렉토리는 `AskUserQuestion`. |
| `add` | **등록(대화형)** | 포트부터 `AskUserQuestion` 으로 받고 동일 절차. |
| `rm <port>` 또는 `remove <port>` | **삭제** | 현재 프로젝트의 그 행을 삭제. 사용자 확인 후. |
| `help` 또는 `-h` | **사용법** | 본 표를 그대로 출력하고 종료. |

## 사용 도구

| 도구 | 용도 |
|:---|:---|
| `Bash` | `port_ops.sh` 호출 (list/list_all/has/add/update/remove/status/kill/start/restart) |
| `AskUserQuestion` | 재시작 시 2+행 선택, 등록 시 서비스/명령/디렉토리 수집, 삭제 시 확인 |
| `Read` | 필요 시 `port_list.md` 원본 표시 |

## 데이터 파일

`$HOME/claude_toolkit/.claude/references/port_list.md` (프로젝트에서는 `.claude/references/port_list.md` 심볼릭 링크).

스키마:

| 열 | 의미 | 비고 |
|---|---|---|
| 프로젝트 | `basename $CLAUDE_PROJECT_DIR` 와 정확히 일치 | 공백 trim |
| 포트 | TCP 포트 번호 | 정수 |
| 서비스 | 사람이 읽는 이름 | 예: "Web UI", "API" |
| 시작명령 | 셸에서 실행할 단일 명령 | 예: `npm run dev`, `uvicorn app:app --port 8000` |
| 작업디렉토리 | 프로젝트 루트 기준 상대경로 | 루트면 `—` |

## 스크립트 인터페이스

`${CLAUDE_PROJECT_DIR}/.claude/skills/port_manager/port_ops.sh` (없으면 `$HOME/claude_toolkit/.claude/skills/port_manager/port_ops.sh`).

```text
# 조회
port_ops.sh list <project>                          # TSV: 포트\t서비스\t시작명령\t작업디렉토리
port_ops.sh list_all                                # port_list.md 전체 그대로
port_ops.sh has  <project> <port>                   # YES(exit 0) / NO(exit 1)

# 편집 (표 mutation)
port_ops.sh add    <project> <port> <service> <cmd> <cwd>
port_ops.sh update <project> <port> <service> <cmd> <cwd>
port_ops.sh remove <project> <port>

# 프로세스
port_ops.sh status  <port>                          # "RUNNING <pid>" | "STOPPED"
port_ops.sh kill    <port>                          # "KILLED <pid>" | "NOT_RUNNING" | "KILL_FAILED <pid>"
port_ops.sh start   <port> <cwd> <cmd...>           # "STARTED pid=<pid> log=<path>"
port_ops.sh restart <port> <cwd> <cmd...>           # kill + start
```

호출 시 항상 `PROJECT_ROOT="$CLAUDE_PROJECT_DIR"` 를 export 한다 (cwd 해석 기준).

## 절차 — 모드별

### 공통 준비

```bash
PROJECT="$(basename "$CLAUDE_PROJECT_DIR")"
OPS="$CLAUDE_PROJECT_DIR/.claude/skills/port_manager/port_ops.sh"
[ -x "$OPS" ] || OPS="$HOME/claude_toolkit/.claude/skills/port_manager/port_ops.sh"
export PROJECT_ROOT="$CLAUDE_PROJECT_DIR"
```

### 모드: 재시작 (인자 없음)

1. `"$OPS" list "$PROJECT"` 로 행 수집.
2. 행 수 분기:
   - **0개**: `[port_manager] <PROJECT> — 등록된 서버 없음. /port_manager <port> 또는 /port_manager add 로 등록하세요.` 출력 후 종료.
   - **1개**: 자동 선택 (한 줄로 표시).
   - **2+개**: `AskUserQuestion` 호출 (§AskUserQuestion 규약).
3. 선택된 행으로 재시작:
   - `"$OPS" status "$PORT"` → `RUNNING <pid>` 이면 알리고 `"$OPS" kill "$PORT"`.
   - `"$OPS" start "$PORT" "$CWD" $CMD` (CMD 는 단어 분리 허용, 따옴표 없이).
   - 2~3초 대기 후 `"$OPS" status "$PORT"` 재확인.
4. 결과 보고 (§출력 형식).

### 모드: 조회 (`show`)

1. `"$OPS" list "$PROJECT"` 결과를 출력 형식 (포트·서비스·시작명령·작업디렉토리) 로 정리해 표시. 재시작 절차는 건너뛴다.
2. 0행이면 미등록 메시지.

### 모드: 전체 조회 (`all` / `list`)

1. `"$OPS" list_all` 결과를 그대로 코드블록으로 출력.

### 모드: 등록·갱신 (`<숫자>` 또는 `add`)

1. **포트 결정**: 인자가 숫자면 그 값. `add` 인자면 `AskUserQuestion` 으로 받기.
2. **충돌 검사**:
   - `"$OPS" has "$PROJECT" "$PORT"` → YES면 갱신 모드, NO면 신규.
   - `grep` 으로 다른 프로젝트가 같은 포트를 쓰는지 확인. 충돌 시 경고를 출력하고 `AskUserQuestion` 으로 진행 여부 확인.
3. **필드 수집** (`AskUserQuestion` 4문항, 한 번에 묶기):
   - 서비스 이름 (예: "Web UI", "API")
   - 시작명령 (예: `npm run dev`)
   - 작업디렉토리 (프로젝트 루트 기준 상대경로; 루트면 `—` 입력 또는 빈칸)
   - 갱신 모드일 때만: 확인 ("기존 행을 갱신하시겠습니까?")
4. **실행**:
   - 신규: `"$OPS" add  "$PROJECT" "$PORT" "<svc>" "<cmd>" "<cwd>"`
   - 갱신: `"$OPS" update "$PROJECT" "$PORT" "<svc>" "<cmd>" "<cwd>"`
5. 결과 행을 출력 형식으로 한 줄 표시.

### 모드: 삭제 (`rm <port>` / `remove <port>`)

1. `"$OPS" has "$PROJECT" "$PORT"` → NO 면 `[port_manager] <PROJECT>:<PORT> — 등록되지 않음.` 종료.
2. 해당 행을 표시한 뒤 `AskUserQuestion` 으로 확인.
3. 확인 시 `"$OPS" remove "$PROJECT" "$PORT"`.

### 모드: 도움말 (`help` / `-h`)

본 SKILL.md 의 §인자 분기 표를 그대로 출력하고 종료. 다른 행동 없음.

## AskUserQuestion 규약

### 재시작 모드 — 2+ 행 선택

```yaml
question: "<PROJECT> 에 등록된 서버가 N개입니다. 어느 것을 재시작할까요?"
header: "서버 선택"
multiSelect: false
options:
  - label: "<SERVICE> :<PORT>"
    description: "<CMD>  @  <CWD>   현재: RUNNING <pid> | STOPPED"
```

- 옵션 description 에는 **현재 상태**(status 결과)를 미리 조회해 포함.
- 행이 4개를 초과하면 처음 3개만 보이고 4번째 옵션은 "그 외 N개는 직접 입력"; 사용자가 Other 로 응답.

### 등록 모드 — 필드 수집

질문 3개 또는 4개를 한 번에 묶어 보낸다 (Other 입력으로 자유 텍스트):

```yaml
- question: "서비스 이름은?"
  header: "서비스"
  options:
    - label: "Web UI"
    - label: "API"
    - label: "Worker"
- question: "시작명령은?"
  header: "시작명령"
  options:
    - label: "npm run dev"
    - label: "uvicorn app:app --reload"
- question: "작업디렉토리는? (프로젝트 루트 기준 상대경로)"
  header: "작업디렉토리"
  options:
    - label: "—  (프로젝트 루트)"
    - label: "web"
    - label: "server"
```

### 삭제 모드 — 확인

```yaml
question: "<PROJECT>:<PORT> (<SERVICE>) 를 정말 삭제할까요?"
header: "삭제 확인"
options:
  - label: "삭제"
  - label: "취소"
```

## 출력 형식

### 재시작 모드 — 1행 자동 선택

```
[port_manager] TaskPilot · Web UI :3000 (자동 선택, 등록 행 1개)
  npm run dev  @  web
  기존: RUNNING 42465  →  KILLED
  신규: RUNNING 51812  (log: /tmp/port_manager/TaskPilot-3000.log)
```

### 조회 모드

```
[port_manager] TaskPilot — 등록된 서버·포트 N개
  3000  Web UI   npm run dev  @  web
  8000  API      uvicorn app:app --reload  @  server
```

비고가 `—` 면 ` @ —` 생략. 0행이면 `[port_manager] TaskPilot — 등록된 서버가 없습니다.`

### 등록·갱신 모드

```
[port_manager] TaskPilot — 신규 등록:
  8000  API   uvicorn app:app --reload  @  server
```

갱신은 `신규 등록` → `행 갱신` 으로 변경.

### 삭제 모드

```
[port_manager] TaskPilot — 행 삭제:
  8000  API   uvicorn app:app --reload  @  server
```

## DO

- 스크립트로 위임한다 — Claude가 `ss`/`lsof`/`kill` 이나 표 마크다운을 직접 다루지 않는다.
- 재시작 모드에서 2+행이면 **반드시** `AskUserQuestion` 으로 사용자에게 묻는다.
- 시작 직후 status 재확인으로 기동 검증.
- 등록 시 다른 프로젝트가 같은 포트를 쓰면 충돌 경고를 띄우고 사용자에게 확인.
- 로그 경로를 결과에 포함해 디버깅 단서를 남긴다.

## DON'T

- `port_list.md` 를 Edit/Write 로 직접 손대지 않는다. 모든 mutation 은 `port_ops.sh add/update/remove` 로.
- 다른 프로젝트의 행을 건드리지 않는다 (전체 조회 외).
- 시작명령을 "유추" 하지 않는다. 필요한 필드는 모두 사용자에게 묻는다.
- 기동 실패 시 자동 재시도 루프를 만들지 않는다.
- 인자가 숫자가 아닌 미지의 문자열이면 추측 실행하지 않는다 — `help` 안내.

## 흔한 함정

| 증상 | 원인 | 해결 |
|:---|:---|:---|
| `RUNNING` 인데 kill 후 다시 `RUNNING` | 부모 프로세스가 자식을 재spawn (예: `next dev` watcher) | `port_ops.sh kill` 은 LISTEN PID만 종료. 부모-자식 트리는 사용자가 직접 처리하도록 안내. |
| `STARTED` 직후 `STOPPED` | 시작명령이 즉시 실패 | 로그 경로 안내. 자동 재시작 안 함. |
| 행이 보이지 않음 | 프로젝트명 대소문자/공백 불일치 | `port_list.md` 첫 컬럼이 `basename $CLAUDE_PROJECT_DIR` 와 정확히 일치해야 함 |
| 표가 깨짐 | 셀에 `|`/`\` 가 들어감 | `port_ops.sh add/update` 가 자동 이스케이프함. Edit 로 수동 편집은 금지. |
| `add` 가 실패 ("row already exists") | 같은 (project,port) 행이 이미 있음 | `update` 사용 또는 먼저 `remove` |

## 체크리스트

- [ ] `$ARGUMENTS` 를 모드 분기 표에 맞게 해석했다.
- [ ] 모든 표 mutation 은 `port_ops.sh` 로 위임했다 (직접 편집 금지).
- [ ] 재시작 모드에서 행 수에 따라 분기(0/1/2+) 했다.
- [ ] 2+ 행에 대해 `AskUserQuestion` 으로 물었다.
- [ ] 등록 모드에서 다른 프로젝트의 포트 충돌을 검사했다.
- [ ] kill 은 RUNNING 일 때만 호출했다.
- [ ] start 후 status 재확인을 수행했다.
- [ ] 결과 보고가 출력 형식을 따른다.
