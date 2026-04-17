---
description: "kimghw/claude_toolkit의 폴더·파일을 현재 프로젝트 .claude/에 심볼릭 링크로 가져옴"
allowed-tools: Bash, Read, Glob
---

# /link_toolkit 명령

인자: $ARGUMENTS

원본 레포(우선순위 순):
1. `/mnt/c/shared_wk/claude_toolkit/` (기본)
2. `/home/kimghw/claude_toolkit/` (폴백 — 1번이 없을 때만 사용)

구조: `agents/`, `commands/`, `skills/`
대상 디렉토리: `<프로젝트 루트>/.claude/`

## 동작 규칙

1. **사전 점검**
   - 원본 경로 결정: `/mnt/c/shared_wk/claude_toolkit/`가 존재하면 이것을 `$TOOLKIT`으로 사용, 없으면 `/home/kimghw/claude_toolkit/`로 폴백. 둘 다 없으면 에러 보고 후 중단.
   - `ls "$TOOLKIT"`로 원본 존재·구조 확인.
   - `ls -la <프로젝트 루트>/.claude/`로 기존 파일/심볼릭 링크 확인.
   - `.claude/`는 프로젝트 `.gitignore`에 등록되어 메인 레포에 커밋되지 않음을 전제로 함.

2. **인자 해석**
   - **인자가 비어 있는 경우**: 원본 하위 구조(agents/commands/skills 및 각 내부 항목)를 나열하고, 어떤 폴더·파일을 링크할지 사용자에게 반드시 확인.
   - **인자가 `all`인 경우**: 최상위 3개 디렉토리(`agents`, `commands`, `skills`)를 `.claude/` 아래에 디렉토리 단위로 링크.
   - **인자가 구체 경로**(예: `skills/pdf2md`, `commands/git.md`)인 경우: 해당 항목만 링크.
   - **여러 항목**을 공백으로 나열 가능 (예: `skills/md2wu commands/git.md`).

3. **링크 생성 규칙**
   - 절대 경로 심볼릭 링크 사용: `ln -s "$TOOLKIT/<rel>" <프로젝트 루트>/.claude/<rel>` (`$TOOLKIT`은 1단계에서 결정한 경로)
   - 대상 경로의 상위 디렉토리가 없으면 `mkdir -p`로 먼저 생성.
   - 이미 같은 이름의 파일/링크가 있으면 **덮어쓰지 말고** 사용자에게 보고 후 지시 대기.
   - 디렉토리 단위 링크(예: `.claude/skills`)와 하위 항목 단위 링크(예: `.claude/skills/pdf2md`)는 충돌하므로, 둘 중 하나만 선택하도록 안내.

4. **사후 확인**
   - `ls -la <프로젝트 루트>/.claude/` 및 생성된 심볼릭 링크의 `readlink`로 타겟이 올바른지 검증.
   - 생성된 링크 목록을 요약 보고.

## 기본 예시

- `/link_toolkit all` → `.claude/agents`, `.claude/commands`, `.claude/skills` 3개 디렉토리 링크
- `/link_toolkit skills/pdf2md skills/md2wu` → `.claude/skills/` 내부에 2개 스킬 개별 링크
- `/link_toolkit` (인자 없음) → 원본 구조 제시 후 사용자에게 선택을 물음
