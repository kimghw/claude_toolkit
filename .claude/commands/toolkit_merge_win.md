---
description: "Windows/복사 방식: claude_toolkit 원본(.project_id ID)을 grep으로 탐지한 뒤 .claude/를 복사 동기화. pull=원본→로컬(교집합), push=로컬→원본+git push"
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion
---

# /toolkit_merge_win 명령

인자: $ARGUMENTS

Windows/WSL 혼용 환경에서 심볼릭 링크가 번거롭거나 동작하지 않을 때 사용한다. 원본 `claude_toolkit` 레포의 `.claude/` 콘텐츠를 **파일 복사**로 현재 프로젝트와 양방향 동기화한다. 심볼릭 방식은 `/toolkit_link` 참조.

## 경로 정의

- **로컬(소비자) 프로젝트**: `$CLAUDE_PROJECT_DIR` — 본 명령을 실행하는 프로젝트 루트. 동기화 대상은 `$CLAUDE_PROJECT_DIR/.claude/`.
- **원본 레포(claude_toolkit)**: 본 문서에서는 `$TOOLKIT`으로 표기. 실제 경로는 아래 **원본 탐지** 절차로 매번 결정한다.
- **원본 식별 ID** (고정 상수, 하드코딩):
  ```
  PROJECT_ID=5a7a5dc046eda268d64df3af621de2c1640f0d66b0abe71fc2509f5e9562b319
  ```
  이 값은 `$TOOLKIT/.project_id` 파일에 기록돼 있으며, 해당 파일을 포함한 디렉토리를 `$TOOLKIT`으로 간주한다.

## 원본 탐지 (모든 동작에 선행, 매번 실행)

1. **환경변수 빠른 경로** — `$CLAUDE_TOOLKIT`가 설정되어 있으면:
   - `grep -q "$PROJECT_ID" "$CLAUDE_TOOLKIT/.project_id" 2>/dev/null` 로 매칭 확인.
   - 일치 → `TOOLKIT="$CLAUDE_TOOLKIT"`로 확정하고 탐색 스킵.
   - 불일치/파일 없음 → 환경변수 무효로 간주. `"CLAUDE_TOOLKIT이 유효하지 않음 — 재탐색합니다"` 고지 후 다음 단계로 폴백.

2. **파일명 기반 탐색 (느린 경로)**:
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
   - 후보 각각에 대해 `grep -l "$PROJECT_ID" <file>` 로 ID 매칭 여부 확인.

3. **매칭 개수별 분기**:
   - **정확히 1개**: 그 파일의 부모 디렉토리를 `$TOOLKIT`으로 확정.
   - **2개 이상**: **`AskUserQuestion`으로 사용자에게 선택을 묻는다**. 각 후보를 `<경로>  (HEAD <shortsha>)` 형식으로 선택지로 제시. 후보가 4개를 넘으면 상위 3개 + `그 외 직접 입력` 옵션으로 구성하고 본문에 전체 목록을 나열한다.
   - **0개**: 에러 고지 후 `AskUserQuestion`(자유 텍스트 입력)으로 `$TOOLKIT` 경로 직접 지정 요청. 입력받은 경로 역시 `.project_id`의 ID가 일치해야 수용, 불일치면 재질의.

4. **확정 후 사후 처리**:
   - 보고: `원본 = <경로>  (HEAD <shortsha>, <clean|dirty>)`.
   - `$CLAUDE_TOOLKIT` 환경변수가 미설정이거나 확정 경로와 다르면, 쉘 rc에 다음을 추가하도록 **안내만** 한다(자동 수정 금지):
     ```
     export CLAUDE_TOOLKIT="<확정 경로>"
     ```
   - **자기 자신 방지**: `realpath "$TOOLKIT"` == `realpath "$CLAUDE_PROJECT_DIR"` 이면 "로컬 == 원본" 에러로 즉시 중단 (claude_toolkit 레포 자체에서 실행된 경우).

## 공통 규칙

- **동기화 대상**: `.claude/` 하위 전체 (`agents/`, `commands/`, `skills/`, `references/`, 기타 파일).
- **제외 (exclude)**:
  - `settings.local.json` — 프로젝트 로컬 설정, 공유 금지.
  - `.project_id` — 원본 식별 파일, 복사 금지.
  - `.git/`, `.DS_Store`, `*.swp`, `*.tmp` — 잡파일.
- **심볼릭 링크 처리**: 로컬 또는 원본 어느 쪽에 심볼릭 링크가 있으면 복사 대신 **스킵**하고 그 사실을 리포트. `/toolkit_link`로 관리 중일 가능성이 있으므로 사용자에게 `/toolkit_link status` 호출을 안내.

## 인자별 동작

### 1. `pull` — 원본 → 로컬, **교집합만**

- 로컬 `.claude/` 기준으로 재귀 순회하며, 각 파일 경로가 `$TOOLKIT/.claude/<rel>`에도 존재하는지 확인.
- **양쪽 모두 존재하는 파일만** 원본 버전으로 덮어쓴다. 원본에만 있는 신규 파일은 **가져오지 않는다** (교집합 원칙).
- 로컬에만 있는 파일(로컬 추가분)은 건드리지 않는다.
- 절차:
  1. 사전 계획: 갱신 예정 목록 / 원본-only 스킵 목록 / 로컬-only 보존 목록을 테이블로 표시하고 사용자 승인 대기.
  2. 변경이 큰 항목은 `diff -u`로 샘플 몇 개를 사전 표시.
  3. 실행: 각 대상에 대해 `cp -f "$TOOLKIT/.claude/<rel>" "$CLAUDE_PROJECT_DIR/.claude/<rel>"`.
- 결과 보고: `갱신 N · 동일 M · 원본-only 스킵 K · 로컬-only 보존 L`.

### 2. `push` — 로컬 → 원본 + `git push`

- 로컬 `.claude/` 하위 전체를 원본 `$TOOLKIT/.claude/` 하위로 복사. 기존 파일은 **덮어쓰기**.
- 원본에만 있던 파일(로컬에 없는 파일)은 **삭제하지 않음** (안전 기본값).
- 절차:
  1. 사전 계획: 복사 대상 / 신규 생성 / 덮어쓰기 목록을 보여주고 사용자 승인 대기.
  2. 실행: `cp -f` 파일 단위 복사, 신규 상위 디렉토리는 `mkdir -p`.
  3. `git -C "$TOOLKIT" status --porcelain .claude` 로 변경 확인.
  4. 변경 없음 → `"푸시할 변경 없음"` 출력 후 종료.
  5. 변경 있음 →
     - `git -C "$TOOLKIT" add -A .claude`
     - `git -C "$TOOLKIT" diff --cached --stat .claude` 표시
     - diff 기반 **한국어 1줄** 커밋 메시지 자동 생성 (예: `commands: toolkit_merge_win 추가, skills/pdf2md 갱신`)
     - `git -C "$TOOLKIT" commit -m "<msg>"`
     - `git -C "$TOOLKIT" push` (upstream 없으면 `-u origin <branch>`)
- 결과 보고: 복사 파일 수, 커밋 해시, push 결과.

### 3. `diff` — 미리보기 (변경 없음)

- pull/push 실행 시 보게 될 계획 테이블만 조회.
- 섹션 분리:
  - `원본 → 로컬 (pull 시 반영될 것)` — 교집합 대상 중 내용이 다른 항목.
  - `로컬 → 원본 (push 시 반영될 것)` — 로컬에 있고 원본과 다르거나 원본에 없는 항목.
- 각 항목: `<rel>   원본-sha vs 로컬-sha (±N줄)` 형식.

### 4. 인자 없음 또는 기타

- 인자 없음 → `diff`와 동일한 미리보기 출력 후, `/toolkit_merge_win pull` 또는 `/toolkit_merge_win push` 호출을 안내.
- 알 수 없는 인자 → 사용법 요약 출력 후 종료.

## 예시

- `/toolkit_merge_win` → 원본 탐지 후 양방향 diff 미리보기.
- `/toolkit_merge_win pull` → 원본의 최신 버전으로 로컬의 기존 파일만 갱신 (신규 파일 추가 없음).
- `/toolkit_merge_win push` → 로컬 수정분을 원본에 복사 후 `git commit + push`.
- `/toolkit_merge_win diff` → 변경 미리보기만, 실제 변경은 수행하지 않음.
