---
description: "선택한 skill/command/agent/reference를 shared_skills_<NN> GitHub 레포로 export하거나(기본), `delete <NN>`로 해당 번들 레포 삭제 (.claude/ 구조 유지, 스냅샷 force-push)"
allowed-tools: Bash, Read, Glob, AskUserQuestion
---

# /export_bundle 명령

인자: $ARGUMENTS

## 개요

toolkit `.claude/` 하위에서 선택한 파일/폴더를 **받는 쪽 레포**(`shared_skills_<NN>`)로 복사해 GitHub에 올린다. 대상 레포는 toolkit과 독립된 임시 공유용 레포이며, 실행마다 스냅샷을 force-push 한다(히스토리 비보존).

## 인자 형식

두 가지 모드가 있다.

**Export 모드 (기본)** — 번들 생성/갱신:
```
/toolkit_export <NN> [--public|--private] <path1> [<path2> ...]
```

**Delete 모드** — 번들 레포 삭제:
```
/toolkit_export delete [<NN1> <NN2> ...]
```

- `<NN>`: 대상 레포 접미사. 영문/숫자/`_`/`-` 허용 (예: `01`, `02a`, `test`). 최종 레포명은 `shared_skills_<NN>`, 소유자는 `gh auth`의 현재 사용자.
- `--public` / `--private`: **최초 생성 시에만 사용**. 기본 `--public`. 이미 존재하면 무시(현재 visibility 유지).
- `<path>`: toolkit `.claude/` 기준 상대 경로. 파일 또는 디렉토리 혼용 가능.
  - 예: `skills/pdf2md`, `skills/md2wu/SKILL.md`, `commands/git.md`, `agents/pdf2md-worker.md`, `references/anthropic-frontmatter.md`
- `delete`: 첫 토큰이 정확히 `delete`면 delete 모드로 전환. 뒤에 오는 `<NN>`들이 삭제 대상. NN이 비면 기존 번들 목록에서 선택받는다.

## 실행 전제

- 본 명령은 **toolkit 레포 루트**에서 실행 (`.claude/`가 실제 파일인 곳). 소비자 프로젝트에서 심볼릭으로 연결된 상태로는 실행하지 말 것.
- `gh` CLI가 인증되어 있어야 함 (`gh auth status`로 확인).
- `git` 사용자 설정 완료 상태 (`user.name`, `user.email`).

## 동작 규칙

### 0. 모드 분기

- 첫 토큰이 정확히 `delete`면 **Delete 모드**로 진입(아래 "Delete 모드" 섹션의 규칙을 따른다).
- 그 외에는 **Export 모드**로 진행(다음 1~9 단계).

### Export 모드

1. **인자 파싱**
   - 첫 토큰을 `<NN>`으로, `--public`/`--private`은 어느 위치에든 올 수 있으니 visibility로 분리, 나머지를 경로 리스트로.
   - `<NN>` 정규식: `^[A-Za-z0-9_-]+$`.

2. **부족/이상 인자 처리 — 에러로 중단하지 말고 사용자에게 물어본다**

   인자가 없거나 형식에 맞지 않으면 `AskUserQuestion` 도구로 **선택지를 제시**해 사용자에게 확정을 받는다. 자유 텍스트 입력을 기대하지 말고, 가능한 값을 조사해 선택지로 노출한다.

   - **`<NN>` 누락 또는 형식 위반**:
     - `gh repo list "$OWNER" --json name --jq '.[].name' | grep '^shared_skills_'`로 기존 번들 레포 목록 조회.
     - 선택지: 기존 번들 각각(`shared_skills_01`, `shared_skills_02`, …) + `새로 만들기`.
     - `새로 만들기` 선택 시 재질문으로 접미사 입력 받기(여전히 정규식 위반이면 다시 질문).
   - **경로 리스트 비어 있음**:
     - `.claude/` 하위 1단계를 스캔(`ls -1 .claude/`)하여 존재하는 최상위 디렉토리/파일을 선택지로 제시(`skills`, `commands`, `agents`, `references` 등 + `전체(.claude 하위 디렉토리 모두)`).
     - 멀티셀렉트 허용. 사용자가 선택한 항목을 그대로 `<path>` 리스트로 사용.
     - 더 세밀한 선택이 필요하면 사용자가 직접 하위 경로를 지정해 재호출하도록 안내.
   - **존재하지 않는 `<path>` 포함**:
     - 어느 경로가 없는지 나열하고, 선택지로 `해당 경로 제거하고 계속` / `중단` 제시.
   - **`--public`/`--private` 충돌(둘 다 지정)**:
     - 둘 중 하나를 선택지로 제시.
   - **최초 생성인데 visibility 미지정**:
     - 기본 `--public`으로 진행하되, 사용자가 쉽게 바꿀 수 있게 `public(기본)` / `private` 선택지 제시. (기존 레포는 visibility 질문 스킵.)

   원칙: "사용자가 한 번 더 타이핑하게" 하는 대신 **수집 가능한 정보로 선택지를 만들어 한 번의 질문으로 끝낸다**. 자유 입력은 불가피할 때만(예: 새 NN 접미사 입력).

3. **사전 검증**
   - `gh auth status` 성공 확인. 실패 시 `gh auth login` 안내 후 중단.
   - `pwd`가 toolkit 레포 루트인지 확인(`.claude/` 존재, `.git/` 존재, `ls -la .claude | grep -v '^l'`로 심볼릭이 아님을 대략 검증).
   - 각 `<path>`에 대해 `$PWD/.claude/<path>` 실존(`test -e`) 검증. 하나라도 없으면 전체 중단.
   - 현재 GitHub 사용자 조회: `OWNER=$(gh api user -q .login)`.

4. **스크래치 디렉토리 준비**
   - `SCRATCH="/tmp/export_bundle/shared_skills_<NN>"`.
   - 기존 디렉토리 있으면 내용 비우기(`rm -rf "$SCRATCH"`). 매 실행 깨끗하게 시작.
   - `mkdir -p "$SCRATCH/.claude"`.

5. **파일 복사 (구조 유지)**
   - 각 `<path>`에 대해:
     - 대상 상위 디렉토리 생성: `mkdir -p "$SCRATCH/.claude/$(dirname <path>)"` (단, `<path>`가 최상위 디렉토리면 `$SCRATCH/.claude/`).
     - 복사: `cp -r "$PWD/.claude/<path>" "$SCRATCH/.claude/<path>"`.
     - 심볼릭 링크 포함되지 않도록 `cp -rL` 고려(내부에서 toolkit 외부를 가리키는 링크가 있을 수 있음). 기본 `-r`로 하되, 복사 후 `find "$SCRATCH" -type l` 결과가 있으면 경고하고 사용자 확인.

6. **README 자동 생성**
   - `$SCRATCH/README.md`에 다음 내용 작성:
     - 번들 이름(`shared_skills_<NN>`), export 시점(ISO8601), export 주체(`$OWNER`).
     - 포함된 경로 목록(복사 대상 `<path>` 리스트).
     - 사용법 안내:
       ```
       # 소비자 프로젝트의 작업 루트에 클론
       cd <작업 루트>
       git clone https://github.com/<OWNER>/shared_skills_<NN>.git

       # 그 후 각 항목을 프로젝트 .claude/ 로 심볼릭 (수동 예시)
       ln -s ../../shared_skills_<NN>/.claude/skills/pdf2md ./project-a/.claude/skills/pdf2md
       ```
     - 원본이 `claude_toolkit` 레포이며 이 번들은 스냅샷이라는 고지.

7. **git 초기화 및 커밋**
   - `cd "$SCRATCH"`.
   - `git init -b main` (항상 main 브랜치 고정).
   - `git add -A`.
   - 커밋 메시지: `snapshot: shared_skills_<NN> @ <UTC timestamp>` (한국어 불필요, 자동화 구분용).
   - `git commit -m ...`.

8. **대상 레포 존재 여부 확인 및 push**
   - `gh repo view "$OWNER/shared_skills_<NN>" >/dev/null 2>&1` 로 존재 확인.
   - **없으면 (최초 생성)**:
     - `gh repo create "$OWNER/shared_skills_<NN>" --<visibility> --source="$SCRATCH" --push`
     - `<visibility>`는 인자에서 파싱한 값(기본 `--public`).
   - **있으면 (갱신)**:
     - `git remote add origin "https://github.com/$OWNER/shared_skills_<NN>.git"`.
     - `git push -f origin main` (force-push로 스냅샷 교체).
     - 최초 생성 시 넘긴 visibility 플래그는 **무시**(이미 존재하므로). 사용자가 visibility 변경을 원하면 별도로 `gh repo edit` 안내.

9. **사후 보고**
   - 최종 URL: `https://github.com/$OWNER/shared_skills_<NN>`.
   - 포함 경로 목록.
   - 모드(최초 생성 / 갱신).
   - 다음 실행 시 경로 세트를 바꾸면 전체 내용이 교체된다는 점 환기(누적 아님).

### Delete 모드

대상: `kimghw` 계정(= `gh auth`의 현재 사용자) 소유 `shared_skills_<NN>` 레포를 GitHub에서 **영구 삭제**한다. 되돌릴 수 없다.

1. **인자 파싱**
   - 첫 토큰 `delete` 제거 후 남은 토큰들을 `<NN>` 리스트로 본다.
   - 각 NN에 대해 정규식 `^[A-Za-z0-9_-]+$` 검증. 위반 항목은 경고하고 리스트에서 제외.

2. **NN 누락 시 사용자에게 선택받기**
   - `OWNER=$(gh api user -q .login)` 조회.
   - `gh repo list "$OWNER" --json name --jq '.[].name' | grep '^shared_skills_'`로 기존 번들 목록 조회.
   - 목록이 비면 "삭제할 대상이 없다"고 보고하고 종료.
   - 목록이 있으면 `AskUserQuestion` 멀티셀렉트로 삭제 대상 선택받음.

3. **존재 확인**
   - 각 `<NN>`에 대해 `gh repo view "$OWNER/shared_skills_<NN>" >/dev/null 2>&1` 로 실제 존재 검증.
   - 없는 항목은 "이미 없음"으로 구분해 보고하고 삭제 리스트에서 제거.

4. **권한 스코프 사전 확인 — 확인 프롬프트보다 먼저**
   - 사용자에게 파괴적 확인을 묻기 전에 토큰이 `delete_repo` 스코프를 가졌는지 검사한다.
   - 검사: `gh auth status 2>&1 | grep -E "Token scopes:.*\\bdelete_repo\\b"` 가 매치되면 OK.
   - **스코프가 없으면 즉시 중단**하고 다음을 안내(자동으로 추가하지 않는다 — 인증 변경은 사용자 의도가 필요하다):
     ```
     gh auth refresh -h github.com -s delete_repo
     ```
     이후 같은 명령을 다시 실행하라고 안내한다. 이 단계에서 막혀야 사용자가 헛된 "삭제 진행" 확인을 하지 않는다.

5. **최종 확인 — 무조건 AskUserQuestion**
   - 삭제 예정 레포의 전체 목록(예: `kimghw/shared_skills_01`, `kimghw/shared_skills_test01`)을 질문 본문에 명시.
   - 선택지: `삭제 진행` / `중단`. 기본 권장은 `중단`(두 번째 옵션이 아니라 첫 번째 옵션이 파괴적이므로 `삭제 진행`에는 "(되돌릴 수 없음)" 같은 경고 문구 첨부).
   - `중단` 선택 시 아무 동작 없이 종료.

6. **삭제 실행**
   - 각 NN에 대해 순차적으로 `gh repo delete "$OWNER/shared_skills_<NN>" --yes` 실행.
   - **토큰 스코프 부족 오류(`delete_repo` 누락)** — 4단계에서 사전 차단되었어야 하지만, 만약 여기서 발생하면 4단계와 동일한 안내 후 중단.
   - 기타 오류(권한, 네트워크 등)는 해당 NN만 실패 처리하고 다음 항목 계속.

7. **사후 보고**
   - 성공 목록, 실패 목록(사유 포함), 이미-없음 목록을 분리해 표시.
   - 로컬 스크래치 디렉토리(`/tmp/export_bundle/shared_skills_<NN>`)가 남아 있으면 `rm -rf`로 같이 정리.

## 예시

- 단일 스킬 최초 공개:
  ```
  /export_bundle 01 --public skills/pdf2md
  ```
  → `https://github.com/<OWNER>/shared_skills_01` (public) 생성, `.claude/skills/pdf2md/` 포함.

- 여러 항목 묶어서 비공개 임시 공유:
  ```
  /export_bundle 02 skills/pdf2md skills/md2wu commands/git.md agents/pdf2md-worker.md
  ```

- 특정 파일만:
  ```
  /export_bundle draft references/anthropic-frontmatter.md references/anthropic-skill-anatomy.md
  ```

- 기존 번들 갱신(스킬 추가):
  ```
  /export_bundle 01 skills/pdf2md skills/md2wu
  ```
  → `shared_skills_01`이 이미 있으므로 force-push, 이전 `skills/pdf2md`만 있던 상태를 두 스킬 포함 상태로 교체.

- 특정 번들 삭제:
  ```
  /toolkit_export delete 01
  ```
  → `kimghw/shared_skills_01` 삭제. 확인 프롬프트 통과 후 `gh repo delete` 실행.

- 여러 번들 동시 삭제:
  ```
  /toolkit_export delete 01 test01
  ```

- 대상 지정 없이 목록에서 고르기:
  ```
  /toolkit_export delete
  ```
  → 기존 `shared_skills_*` 목록을 보여주고 멀티셀렉트로 선택 → 확인 → 삭제.

## 주의

- **누적 아님**: 각 실행은 해당 `<NN>` 레포의 전체 콘텐츠를 인자로 지정한 경로 세트로 교체한다. 이전 내용을 유지하려면 경로를 다시 모두 지정해야 함.
- **히스토리 없음**: 매 실행 `git init` 후 force-push 이므로 대상 레포 커밋 히스토리는 매번 1개로 재설정된다.
- **민감 정보 점검**: 복사 전 대상 파일에 토큰/경로 등 비공개 정보가 없는지 사용자 책임. `--public` 사용 시 특히 주의.
- **심볼릭 링크**: `.claude/` 하위에 외부를 가리키는 심볼릭이 있으면 복사 결과가 의도와 다를 수 있음. 4단계에서 경고 후 확인.
- **Delete는 되돌릴 수 없음**: `gh repo delete`는 GitHub 상에서 영구 삭제이며 복구 불가. 확인 프롬프트에서 `삭제 진행`을 선택하기 전에 번들 이름을 다시 한 번 읽어볼 것.
- **Delete 권한 스코프**: `gh` 토큰에 `delete_repo` 스코프가 필요. 누락 시 `gh auth refresh -h github.com -s delete_repo`로 추가해야 하며, 명령이 자동으로 수행하지 않는다.
