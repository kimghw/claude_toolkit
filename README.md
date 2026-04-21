# claude_toolkit

Claude Code용 공용 명령·스킬·에이전트·레퍼런스 모음. 각 프로젝트의 `.claude/`로 심볼릭 링크하여 재사용한다.

## 설치 위치

### 지원 환경

이 레포는 Windows 네이티브 셸(PowerShell, Git Bash)과 Ubuntu/WSL에서 동일하게 동작한다. 소비자 프로젝트의 `.claude/` 하위는 이 레포로 심볼릭 링크되며, 한 머신에서 같은 NTFS 경로를 양쪽에서 공유하면 한쪽에서 건 링크가 반대편에서도 해석된다.

전형적 설치 위치:

- Windows 네이티브: `C:\claude_toolkit\claude_toolkit`, `%USERPROFILE%\claude_toolkit`
- Ubuntu/WSL: `$HOME/claude_toolkit`, `/mnt/c/<공유폴더>/claude_toolkit` (Windows NTFS를 WSL에서 공유해 양쪽에서 쓰는 형태)

도구는 원본 위치를 (1) env `CLAUDE_TOOLKIT_ROOT`, (2) 소비자 프로젝트의 형제 경로, (3) `$HOME/claude_toolkit`(Ubuntu/WSL), (4) `%USERPROFILE%\claude_toolkit`(Windows) 순으로 해석한다. `CLAUDE_TOOLKIT_ROOT` 환경 변수로 언제든 오버라이드 가능.

### 권장 레이아웃

이 레포는 **사용하려는 프로젝트들과 동일한 경로 레벨**(형제 디렉토리)에 클론한다. `/toolkit_link`가 상위 경로 기준으로 원본을 찾고, 각 프로젝트 `.claude/`에서 toolkit 쪽으로 절대 경로 심볼릭을 걸기 때문이다.

권장 레이아웃 (작업 루트는 환경에 따라 `~/`, `C:\`, `/mnt/c/shared_wk/` 등 자유):

```
<작업 루트>/
├── claude_toolkit/      ← 본 레포를 여기에 클론
├── project-a/
├── project-b/
└── project-c/
```

예시 — WSL에서 NTFS 공유 경로 `/mnt/c/shared_wk/` 아래에 프로젝트들이 있고 Windows 측에서도 `C:\shared_wk\`로 그대로 접근하는 경우:

```bash
cd /mnt/c/shared_wk
git clone https://github.com/kimghw/claude_toolkit.git
```

toolkit을 프로젝트 하위(`<project>/claude_toolkit/`)나 상위(`<작업 루트>/../`)에 두지 말 것 — 링크 해석이 어긋난다.

심볼릭 링크 생성(참고):

- Windows: `New-Item -ItemType SymbolicLink -Path <링크> -Target <원본>` 또는 `mklink /D <링크> <원본>` (개발자 모드 활성화 또는 관리자 권한 필요).
- Ubuntu/WSL: `ln -s <원본> <링크>`.

## 사용

대상 프로젝트 루트에서:

```
/toolkit_link all
```

프로젝트 `.claude/` 하위에 toolkit의 `agents/`·`commands/`·`skills/`가 심볼릭으로 연결된다. 부분 연결·promote(로컬→원본 승격)·unlink는 [`.claude/commands/toolkit_link.md`](.claude/commands/toolkit_link.md) 참조.

## 배치 및 호출 흐름

```
<작업 루트>/
│
├── claude_toolkit/                     ← 원본 (본 레포, git 관리)
│   └── .claude/
│       ├── agents/       ┐
│       ├── commands/     │  ← 실제 콘텐츠는 전부 여기
│       ├── skills/       │
│       └── references/   ┘
│                ▲
│                │ (symlink 해석 시 여기로 도달)
│                │
├── project-a/   │                      ← 소비자 프로젝트
│   └── .claude/ │                      (project 자체 .gitignore 처리)
│       ├── agents    ──┐
│       ├── commands   ─┼──→ ../claude_toolkit/.claude/{agents,commands,skills}
│       └── skills     ─┘
│
└── project-b/                          ← 소비자 프로젝트 (동일 패턴)
    └── .claude/
        ├── agents    ──→ ../claude_toolkit/.claude/agents
        ├── commands  ──→ ../claude_toolkit/.claude/commands
        └── skills    ──→ ../claude_toolkit/.claude/skills
```

> 위 심볼릭 화살표(`../claude_toolkit/...`)는 Windows 네이티브와 Ubuntu/WSL 양쪽에서 동일하게 해석된다. 같은 NTFS 경로를 공유하면 한쪽에서 건 링크가 반대편에서도 유효.

호출 흐름:

```
 사용자  ──(1) cd project-a && claude ──▶  Claude Code
                                              │
                                              │ (2) .claude/ 로드
                                              ▼
                               project-a/.claude/commands/git.md
                                              │
                                              │ (3) symlink 해석
                                              ▼
                  claude_toolkit/.claude/commands/git.md  ← 실제 실행 대상
```

1. 사용자가 `project-a`에서 Claude Code 실행.
2. Claude Code가 `project-a/.claude/`의 command·skill·agent description을 로드.
3. `/git` 등 호출 시 심볼릭이 해석되어 toolkit 원본이 실행됨. toolkit을 업데이트하면 모든 소비자 프로젝트에 즉시 반영.
