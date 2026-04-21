# claude_toolkit

Claude Code용 공용 명령·스킬·에이전트·레퍼런스 모음. 각 프로젝트의 `.claude/`로 심볼릭 링크하여 재사용한다.

## 설치 위치

이 레포는 **사용하려는 프로젝트들과 동일한 경로 레벨**(형제 디렉토리)에 클론한다. `/toolkit_link_symbolic`이 상위 경로 기준으로 원본을 찾고, 각 프로젝트 `.claude/`에서 toolkit 쪽으로 절대 경로 심볼릭을 걸기 때문이다.

권장 레이아웃 (작업 루트는 환경에 따라 `~/`, `~/<user>/`, `/mnt/c/shared_wk/` 등 자유):

```
<작업 루트>/
├── claude_toolkit/      ← 본 레포를 여기에 클론
├── project-a/
├── project-b/
└── project-c/
```

예시 — WSL에서 `/mnt/c/shared_wk/` 아래에 프로젝트들이 있는 경우:

```bash
cd /mnt/c/shared_wk
git clone https://github.com/kimghw/claude_toolkit.git
```

toolkit을 프로젝트 하위(`<project>/claude_toolkit/`)나 상위(`<작업 루트>/../`)에 두지 말 것 — 링크 해석이 어긋난다.

## 사용

대상 프로젝트 루트에서:

```
/toolkit_link_symbolic all
```

프로젝트 `.claude/` 하위에 toolkit의 `agents/`·`commands/`·`skills/`가 심볼릭으로 연결된다. 부분 연결·promote(로컬→원본 승격)·unlink는 [`.claude/commands/toolkit_link_symbolic.md`](.claude/commands/toolkit_link_symbolic.md) 참조.
