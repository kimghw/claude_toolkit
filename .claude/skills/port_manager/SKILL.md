---
name: port_manager
description: 현재 프로젝트의 서버·포트를 SSOT(port_list.md)에서 조회·등록·갱신·삭제하고, 등록된 서버를 상태확인→종료→재시작까지 처리. 행이 0이면 등록 안내, 1이면 자동 재시작, 2+이면 AskUserQuestion으로 선택받아 재시작. 포트 검색·종료·기동·표 편집은 port_ops.sh 스크립트로 위임. TRIGGER when 사용자가 /port_manager 호출, 현재 프로젝트 포트·서버 등록·조회·재시작·재기동 요청. DO NOT TRIGGER when 외부 호스트 접속, 배포·CI 파이프라인.
allowed-tools: Bash AskUserQuestion Read
argument-hint: [show|all|update|add|<port>|rm <port>|help]
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
| `update` | **자동 발견 등록** | 현재 프로젝트에 속한 LISTEN 서버를 `discover` 로 찾아 보여주고, `AskUserQuestion` multiSelect 로 등록 대상을 고르게 한다. 다른 프로젝트와 같은 포트면 충돌 경고. |
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

**스킬 폴더 안**에서 관리한다 — `.claude/skills/port_manager/port_list.md` (claude_toolkit 원본: `$HOME/claude_toolkit/.claude/skills/port_manager/port_list.md`). 여러 프로젝트가 같은 toolkit 을 공유하므로 한 파일이 모든 프로젝트의 SSOT 역할을 유지한다. `port_ops.sh` 는 스크립트와 같은 폴더의 `port_list.md` 를 기본 경로로 사용한다 (override 가 필요하면 환경변수 `PORT_LIST` 로).

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

# 자동 발견
port_ops.sh discover [project_root]                 # TSV: 포트\tPID\t시작명령\t작업디렉토리 (PROJECT_ROOT 안에 속한 LISTEN 만)
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
4. 결과 보고 (§출력 형식). **기동 성공 시 클릭 가능한 URL 링크를 별도 줄에 출력한다** — 반드시 코드블록(``` ```) 바깥에 마크다운 하이퍼링크 형식 `👉 [http://localhost:<PORT>](http://localhost:<PORT>)` 로. 코드블록 내부에 두면 클릭이 안 되므로 금지.

### 모드: 조회 (`show`)

1. `"$OPS" list "$PROJECT"` 결과를 출력 형식 (포트·서비스·시작명령·작업디렉토리) 로 정리해 표시. 재시작 절차는 건너뛴다.
2. 0행이면 미등록 메시지.

### 모드: 전체 조회 (`all` / `list`)

1. `"$OPS" list_all` 결과를 그대로 코드블록으로 출력.

### 모드: 자동 발견 등록 (`update`)

현재 프로젝트에서 이미 떠 있는 서버를 스캔해 SSOT 에 일괄 등록·갱신한다. **포트 충돌(다른 프로젝트가 같은 포트 사용)을 보여주는 것**이 핵심.

1. `"$OPS" discover "$CLAUDE_PROJECT_DIR"` 로 후보 수집 (TSV: 포트·PID·시작명령·작업디렉토리).
2. 0행이면 `[port_manager] <PROJECT> — 실행 중인 서버를 찾지 못했습니다. 서버를 먼저 띄운 뒤 다시 실행하거나 /port_manager add 로 수동 등록하세요.` 출력 후 종료.
3. 각 후보에 대해 분류:
   - `"$OPS" has "$PROJECT" "$PORT"` → YES면 **등록됨** (갱신 후보), NO면 신규.
   - 신규 중 같은 포트가 다른 프로젝트 행에 있으면 **충돌** 라벨. (`grep` 으로 `port_list.md` 의 해당 포트 행을 찾아 프로젝트명 비교)
4. 후보 표를 출력 형식대로 보여준다 (라벨: `[신규]`, `[등록됨]`, `[충돌: <다른프로젝트>]`).
5. `AskUserQuestion` (**multiSelect: true**) 로 등록·갱신할 항목을 고르게 한다 (§AskUserQuestion 규약).
6. 선택된 각 항목에 대해 서비스 이름을 묻는다 (`AskUserQuestion`; 한 번에 묶어서). 시작명령·작업디렉토리는 detect 값을 기본으로 쓰되, 사용자가 Other 로 수정 가능. `next-server` 처럼 자식 프로세스만 잡힌 경우 사용자가 `npm run dev` 등 상위 명령으로 바꿀 수 있도록 안내한다.
7. 실행:
   - 신규: `"$OPS" add  "$PROJECT" "$PORT" "<svc>" "<cmd>" "<cwd>"`
   - 등록됨(갱신): `"$OPS" update "$PROJECT" "$PORT" "<svc>" "<cmd>" "<cwd>"`
   - 충돌: 사용자가 **그대로 진행 선택 시**에만 add. (충돌 그 자체로는 차단하지 않지만, 같은 포트를 두 프로젝트가 동시에 쓸 수 없다는 점을 경고로 명시한다.)
8. 결과 행들을 출력 형식으로 정리해 보여준다.

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

### 자동 발견 모드 — 등록 대상 선택 (multiSelect)

```yaml
question: "<PROJECT> 에서 실행 중인 서버 N개를 찾았습니다. SSOT 에 등록·갱신할 항목을 모두 고르세요."
header: "등록 대상"
multiSelect: true
options:
  - label: "<PORT> · <SERVICE_INFERRED>"
    description: "[신규|등록됨|충돌:<other-proj>]  <CMD>  @  <CWD>   pid=<PID>"
```

- 옵션 label 의 `SERVICE_INFERRED` 는 cmdline 의 첫 토큰이나 알기 쉬운 키워드(예: `next-server` → "Web UI"). 추론이 어렵으면 `port:<PORT>` 만.
- description 에 분류 라벨을 **맨 앞**에 넣어 사용자가 충돌을 한눈에 본다.
- 후보가 4개 초과면 처음 3개 + Other "직접 입력".

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

상태/로그 블록은 코드펜스 안, URL 하이퍼링크는 **반드시 코드펜스 바깥**에 별도 줄로 출력한다 (그래야 클릭 가능).

```
[port_manager] TaskPilot · Web UI :3000 (자동 선택, 등록 행 1개)
  npm run dev  @  web
  기존: RUNNING 42465  →  KILLED
  신규: RUNNING 51812  (log: /tmp/port_manager/TaskPilot-3000.log)
```

👉 [http://localhost:3000](http://localhost:3000)

URL 줄은 **기동 후 status 재확인이 `RUNNING` 일 때만** 출력한다. `STOPPED` 면 URL 줄을 생략하고 로그 경로 안내만 남긴다.

### 조회 모드

표 본문은 코드펜스 안에, **클릭 가능한 URL 목록은 코드펜스 바깥에 별도 섹션**으로 출력한다.

```
[port_manager] TaskPilot — 등록된 서버·포트 N개
  3000  Web UI   npm run dev  @  web
  8000  API      uvicorn app:app --reload  @  server
```

- 👉 [http://localhost:3000](http://localhost:3000) — Web UI
- 👉 [http://localhost:8000](http://localhost:8000) — API

비고가 `—` 면 ` @ —` 생략. 0행이면 `[port_manager] TaskPilot — 등록된 서버가 없습니다.` (URL 섹션 생략)

### 등록·갱신 모드

```
[port_manager] TaskPilot — 신규 등록:
  8000  API   uvicorn app:app --reload  @  server
```

갱신은 `신규 등록` → `행 갱신` 으로 변경.

### 자동 발견 모드 (`update`)

후보 표시 단계 — 라벨을 맨 앞에 둬 충돌을 한눈에 확인:

```
[port_manager] TaskPilot — 발견된 서버 N개
  [신규]              3000  next-server      pid=532946  @  web
  [등록됨]            8000  uvicorn          pid=611002  @  server
  [충돌: OtherProj]   5173  vite             pid=712345  @  web
```

처리 결과:

```
[port_manager] TaskPilot — 자동 발견 등록 결과:
  + 신규  3000  Web UI   npm run dev  @  web
  ~ 갱신  8000  API      uvicorn app:app --reload  @  server
```

- `+` = 신규 add, `~` = 기존 행 update, `=` = 변경 없이 건너뜀.
- 0건이면 `[port_manager] TaskPilot — 등록한 행이 없습니다.`

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
- **URL은 코드블록 바깥에 마크다운 하이퍼링크로 출력한다** — `👉 [http://localhost:<PORT>](http://localhost:<PORT>)`. 코드펜스 안에 두면 클릭이 안 된다.

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
- [ ] `update` 모드에서 `discover` 결과를 분류(신규/등록됨/충돌)해 사용자에게 보여줬다.
- [ ] `update` 모드 multiSelect 선택 결과만 add/update 했다 (선택 안 한 행은 건드리지 않음).
- [ ] kill 은 RUNNING 일 때만 호출했다.
- [ ] start 후 status 재확인을 수행했다.
- [ ] 결과 보고가 출력 형식을 따른다.
