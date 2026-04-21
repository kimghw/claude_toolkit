---
description: "kimghw/claude_toolkit와 현재 프로젝트 .claude/를 심볼릭 링크로 연결 (pull: 원본→로컬, promote: 로컬→원본, unlink: 로컬 링크 제거)"
allowed-tools: Bash, Read, Glob
---

# /link_toolkit 명령

인자: $ARGUMENTS

## 경로 정의

- **원본 레포(claude_toolkit) 위치**: `<프로젝트 루트>` — 본 문서에서 claude_toolkit 레포 루트를 가리키는 기호. 설치 위치가 바뀌면 이 표기만 기준으로 해석하면 됨. 이하 본문에서는 `$TOOLKIT`으로 참조.
- **원본 콘텐츠 디렉토리**: `$TOOLKIT/.claude/` — 이 레포는 자체적으로 `.claude/` 하위에 `agents/`, `commands/`, `skills/`, `references/`를 보관한다. 심볼릭 원본은 모두 이 경로 하위.
- **로컬 대상(소비자 프로젝트)**: `$CLAUDE_PROJECT_DIR` — 본 명령을 실행하는 현재 프로젝트 루트. `.claude/`가 생성/수정되는 위치.

## 동작 모드

각 인자(경로)에 대해 **상태를 먼저 판별**한 뒤 모드를 결정한다. 인자 하나하나를 독립적으로 처리한다. 사용자가 넘기는 `<rel>`(예: `commands/git.md`)은 **소비자 `.claude/` 기준 상대 경로**이며, 원본 측에서는 `$TOOLKIT/.claude/<rel>`로 해석한다.

| 로컬(`.claude/<rel>`) | 원본(`$TOOLKIT/.claude/<rel>`) | 모드 |
|---|---|---|
| 없음 | 있음 | **pull**: 원본 → 로컬 심볼릭 생성 |
| 실파일/실디렉토리 | 없음 | **promote**: 로컬 → 원본으로 이동 후 심볼릭으로 대체 |
| 심볼릭(원본 가리킴) | 있음 | **skip**: 이미 연결됨, 보고만 |
| 실파일/실디렉토리 | 있음 | **conflict**: 양쪽 존재 → 사용자 확인 후 선택 |
| 없음 | 없음 | **error**: 경로 없음 보고 |

## 동작 규칙

1. **사전 점검**
   - `$TOOLKIT`(= `<프로젝트 루트>`) 실제 경로를 확인. 없거나 접근 불가면 에러 후 중단하고 사용자에게 설치 위치를 물음.
   - `ls "$TOOLKIT/.claude"` 및 `ls -la "$CLAUDE_PROJECT_DIR/.claude/"`로 양쪽 구조 확인.
   - 소비자 프로젝트의 `.claude/`는 일반적으로 소비자 `.gitignore`에 등록되어 소비자 레포에 커밋되지 않음을 전제로 함. (toolkit 원본 레포에서는 `.claude/`가 트래킹 대상.)

2. **인자 해석**
   - **인자 없음**: 원본 하위 구조와 로컬 `.claude/` 상태(실파일 vs 심볼릭)를 함께 제시하고, 어떤 항목을 어떤 모드로 처리할지 사용자 확인.
   - **`all`**: 최상위 3개(`agents`, `commands`, `skills`)를 `.claude/`에 디렉토리 단위로 **pull-link**.
   - **구체 경로**(예: `references`, `skills/pdf2md`, `commands/git.md`): 위 상태표에 따라 **모드 자동 판별**.
   - **여러 항목**: 공백으로 나열 가능 (예: `references skills/md2wu`). 각 항목 독립 처리.
   - **`unlink <경로> [<경로> ...]`**: 지정한 경로의 심볼릭 링크만 선택적으로 제거 (아래 5-1 참조).
   - **`unlink all`**: `.claude/` 하위에서 `$TOOLKIT/.claude/`를 가리키는 **모든** 심볼릭 링크를 일괄 제거.

3. **pull 모드** (원본 → 로컬 심볼릭)
   - 절대 경로 심볼릭 사용: `ln -s "$TOOLKIT/.claude/<rel>" "$CLAUDE_PROJECT_DIR/.claude/<rel>"`
   - 대상 상위 디렉토리가 없으면 `mkdir -p`로 먼저 생성.
   - 디렉토리 단위 링크(예: `.claude/skills`)와 하위 항목 링크(예: `.claude/skills/pdf2md`)는 충돌하므로 둘 중 하나만 선택하도록 안내.

4. **promote 모드** (로컬 → 원본 이동 후 심볼릭으로 대체)
   - 실행 전 사용자 확인 필수: "이 경로를 toolkit 원본으로 이동한 뒤 심볼릭으로 대체합니다" 요약 후 승인 대기.
   - 순서:
     1. 대상 상위 디렉토리 생성: `mkdir -p "$(dirname "$TOOLKIT/.claude/<rel>")"`
     2. 이동: `mv "$CLAUDE_PROJECT_DIR/.claude/<rel>" "$TOOLKIT/.claude/<rel>"`
     3. 심볼릭 생성: `ln -s "$TOOLKIT/.claude/<rel>" "$CLAUDE_PROJECT_DIR/.claude/<rel>"`
     4. 검증: `readlink` 결과가 `$TOOLKIT/.claude/<rel>`와 일치하는지 확인.
   - toolkit 레포에 add/commit/push는 **이 명령이 자동으로 하지 않는다**. `/toolkit_git`로 별도 커밋하도록 안내만.
   - 이동 중 에러 시 즉시 중단하고 현재 상태(이동됐는지 여부)를 보고.

5. **conflict / skip / error**
   - conflict: 양쪽 모두 존재 → 어떤 쪽을 정본으로 살릴지(로컬 버리고 pull / 원본 버리고 promote / 수동 머지) 사용자에게 확인.
   - skip: 이미 올바른 심볼릭이면 "이미 연결됨"으로 보고만.
   - error: 양쪽 다 없으면 경로 오타 가능성 보고.

5-1. **unlink 모드** (로컬 심볼릭 링크 제거)
   - **대상 판별**: 각 경로에 대해 `test -L "$CLAUDE_PROJECT_DIR/.claude/<rel>"` 로 심볼릭 여부 확인.
     - **실파일/실디렉토리**: 제거 거부 (데이터 손실 위험). "심볼릭이 아닙니다" 보고 후 스킵.
     - **없음**: "대상 없음" 보고 후 스킵.
     - **심볼릭이지만 `$TOOLKIT/.claude/`를 가리키지 않음**: 외부 링크일 수 있으므로 기본 스킵. 강제 제거는 사용자 명시적 확인 필요.
     - **심볼릭이고 `$TOOLKIT/.claude/` 하위를 가리킴**: 제거 대상.
   - **사전 확인**: 제거할 링크 목록을 `경로 → 원본` 형식으로 표시하고 사용자 승인 대기.
   - **실행**: `rm "$CLAUDE_PROJECT_DIR/.claude/<rel>"` (심볼릭 자체만 제거, 원본 `$TOOLKIT/.claude/<rel>`은 그대로 유지).
   - **`unlink all`**: `find "$CLAUDE_PROJECT_DIR/.claude/" -maxdepth 3 -type l` 로 심볼릭만 나열하고, `readlink`로 `$TOOLKIT/.claude/` 프리픽스를 가진 것만 필터링하여 일괄 제거 후보로 제시.
   - **사후 검증**: 제거된 경로에 `ls` 해서 없어졌는지 확인. 처리 결과는 6번 사후 확인에 포함.
   - 원본(`$TOOLKIT/.claude/<rel>`)은 절대 건드리지 않음. 원본까지 지우려면 toolkit 레포에서 직접 작업.

6. **사후 확인**
   - `ls -la "$CLAUDE_PROJECT_DIR/.claude/<rel 상위>"` 및 `readlink`로 링크 검증.
   - 처리된 항목별로 `모드 | 경로 | 결과` 요약 보고.

## 예시

- `/link_toolkit all` → 3개 최상위 디렉토리 pull-link
- `/link_toolkit skills/pdf2md skills/md2wu` → 2개 스킬 pull-link
- `/link_toolkit references` → 로컬 `.claude/references/`가 실디렉토리이고 원본에 없으면 **promote** (toolkit으로 이동 후 심볼릭 대체)
- `/link_toolkit unlink skills/pdf2md` → 해당 심볼릭 링크만 제거 (원본은 보존)
- `/link_toolkit unlink skills/pdf2md commands/git.md` → 여러 링크 선택 제거
- `/link_toolkit unlink all` → `.claude/` 내 toolkit 대상 심볼릭 링크 일괄 제거
- `/link_toolkit` (인자 없음) → 원본/로컬 상태 제시 후 사용자에게 선택을 물음
