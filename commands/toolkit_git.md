---
description: "claude_toolkit 레포 git 자동화. 인자 없으면 stage+commit, 'push'면 push"
allowed-tools: Bash, Read, Grep, Glob
---

# /toolkit_git 명령

인자: $ARGUMENTS

대상 레포: `/mnt/c/shared_wk/claude_toolkit`

## 동작 규칙

1. **인자가 비어 있거나 없는 경우** (기본 동작):
   - `git -C /mnt/c/shared_wk/claude_toolkit add -A`로 모든 변경사항 스테이지
   - `git -C /mnt/c/shared_wk/claude_toolkit diff --cached --stat`으로 스테이지된 내용 확인
   - 변경사항이 없으면 "커밋할 내용 없음" 출력 후 종료
   - 변경사항이 있으면 diff를 분석해 간결한 커밋 메시지 자동 생성 (한국어, 1줄)
   - `git -C /mnt/c/shared_wk/claude_toolkit commit`으로 커밋

2. **인자가 `push`인 경우**:
   - `git -C /mnt/c/shared_wk/claude_toolkit push`로 푸시 (upstream 없으면 `-u origin <branch>` 사용)

3. **그 외 인자**:
   - 인자를 그대로 `git -C /mnt/c/shared_wk/claude_toolkit` 뒤에 전달하여 실행
