---
description: "kimghw/claude_toolkit와 현재 프로젝트 .claude/를 심볼릭 링크로 연결 (pull: 원본→로컬, promote: 로컬→원본)"
allowed-tools: Bash, Read, Glob
---

# /link_toolkit 명령

인자: $ARGUMENTS

원본 레포(우선순위 순):
1. `/mnt/c/shared_wk/claude_toolkit/` (기본)
2. `/home/kimghw/claude_toolkit/` (폴백 — 1번이 없을 때만 사용)

대상 디렉토리: `<프로젝트 루트>/.claude/`

## 동작 모드

각 인자(경로)에 대해 **상태를 먼저 판별**한 뒤 모드를 결정한다. 인자 하나하나를 독립적으로 처리한다.

| 로컬(`.claude/<경로>`) | 원본(`$TOOLKIT/<경로>`) | 모드 |
|---|---|---|
| 없음 | 있음 | **pull**: 원본 → 로컬 심볼릭 생성 |
| 실파일/실디렉토리 | 없음 | **promote**: 로컬 → 원본으로 이동 후 심볼릭으로 대체 |
| 심볼릭(원본 가리킴) | 있음 | **skip**: 이미 연결됨, 보고만 |
| 실파일/실디렉토리 | 있음 | **conflict**: 양쪽 존재 → 사용자 확인 후 선택 |
| 없음 | 없음 | **error**: 경로 없음 보고 |

## 동작 규칙

1. **사전 점검**
   - 원본 경로 결정: `/mnt/c/shared_wk/claude_toolkit/`가 존재하면 `$TOOLKIT`으로 사용, 없으면 `/home/kimghw/claude_toolkit/`로 폴백. 둘 다 없으면 에러 후 중단.
   - `ls "$TOOLKIT"` 및 `ls -la <프로젝트 루트>/.claude/`로 양쪽 구조 확인.
   - `.claude/`는 프로젝트 `.gitignore`에 등록되어 메인 레포에 커밋되지 않음을 전제로 함.

2. **인자 해석**
   - **인자 없음**: 원본 하위 구조와 로컬 `.claude/` 상태(실파일 vs 심볼릭)를 함께 제시하고, 어떤 항목을 어떤 모드로 처리할지 사용자 확인.
   - **`all`**: 최상위 3개(`agents`, `commands`, `skills`)를 `.claude/`에 디렉토리 단위로 **pull-link**.
   - **구체 경로**(예: `references`, `skills/pdf2md`, `commands/git.md`): 위 상태표에 따라 **모드 자동 판별**.
   - **여러 항목**: 공백으로 나열 가능 (예: `references skills/md2wu`). 각 항목 독립 처리.

3. **pull 모드** (원본 → 로컬 심볼릭)
   - 절대 경로 심볼릭 사용: `ln -s "$TOOLKIT/<rel>" <프로젝트 루트>/.claude/<rel>`
   - 대상 상위 디렉토리가 없으면 `mkdir -p`로 먼저 생성.
   - 디렉토리 단위 링크(예: `.claude/skills`)와 하위 항목 링크(예: `.claude/skills/pdf2md`)는 충돌하므로 둘 중 하나만 선택하도록 안내.

4. **promote 모드** (로컬 → 원본 이동 후 심볼릭으로 대체)
   - 실행 전 사용자 확인 필수: "이 경로를 toolkit 원본으로 이동한 뒤 심볼릭으로 대체합니다" 요약 후 승인 대기.
   - 순서:
     1. 대상 상위 디렉토리 생성: `mkdir -p "$(dirname "$TOOLKIT/<rel>")"`
     2. 이동: `mv "<프로젝트 루트>/.claude/<rel>" "$TOOLKIT/<rel>"`
     3. 심볼릭 생성: `ln -s "$TOOLKIT/<rel>" "<프로젝트 루트>/.claude/<rel>"`
     4. 검증: `readlink` 결과가 `$TOOLKIT/<rel>`와 일치하는지 확인.
   - toolkit 레포에 add/commit/push는 **이 명령이 자동으로 하지 않는다**. `/toolkit_git`로 별도 커밋하도록 안내만.
   - 이동 중 에러 시 즉시 중단하고 현재 상태(이동됐는지 여부)를 보고.

5. **conflict / skip / error**
   - conflict: 양쪽 모두 존재 → 어떤 쪽을 정본으로 살릴지(로컬 버리고 pull / 원본 버리고 promote / 수동 머지) 사용자에게 확인.
   - skip: 이미 올바른 심볼릭이면 "이미 연결됨"으로 보고만.
   - error: 양쪽 다 없으면 경로 오타 가능성 보고.

6. **사후 확인**
   - `ls -la <프로젝트 루트>/.claude/<rel 상위>` 및 `readlink`로 링크 검증.
   - 처리된 항목별로 `모드 | 경로 | 결과` 요약 보고.

## 예시

- `/link_toolkit all` → 3개 최상위 디렉토리 pull-link
- `/link_toolkit skills/pdf2md skills/md2wu` → 2개 스킬 pull-link
- `/link_toolkit references` → 로컬 `.claude/references/`가 실디렉토리이고 원본에 없으면 **promote** (toolkit으로 이동 후 심볼릭 대체)
- `/link_toolkit` (인자 없음) → 원본/로컬 상태 제시 후 사용자에게 선택을 물음
