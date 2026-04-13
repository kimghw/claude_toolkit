---
description: "git 작업 자동화. 인자 없으면 stage+commit+push, 'pull'이면 pull"
allowed-tools: Bash, Read, Grep, Glob
---

# /git 명령

인자: $ARGUMENTS

## 동작 규칙

1. **인자가 비어 있거나 없는 경우** (기본 동작):
   - `git add -A`로 모든 변경사항 스테이지
   - `git diff --cached --stat`으로 스테이지된 내용 확인
   - 변경사항이 없으면 "커밋할 내용 없음" 출력 후 종료
   - 변경사항이 있으면 diff를 분석해 간결한 커밋 메시지 자동 생성 (한국어, 1줄)
   - `git commit`으로 커밋
   - `git push`로 현재 브랜치에 푸시 (upstream 없으면 `-u origin <branch>` 사용)

2. **인자가 `pull`인 경우**:
   - `git pull`을 실행하고 결과를 보여줌

3. **그 외 인자**:
   - 인자를 그대로 `git` 명령의 서브커맨드로 전달하여 실행 (예: `/git status` → `git status`)
