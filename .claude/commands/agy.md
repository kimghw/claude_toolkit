# /agy — Antigravity CLI(agy) 실행 + 모델 관리 도우미

사용자가 `/agy` 를 호출하면 아래 규칙에 따라 동작한다. 인자는 `$ARGUMENTS` 로 전달된다.

## 동작 규칙 (인자 라우팅)
- `$ARGUMENTS` 가 **`model` 로 시작**하면 → "모델 관리" 모드로 분기(아래 ▶ 모델 관리 참조):
  - `model` 만 (라벨 없음) → **AskUserQuestion으로 등록된 모델 중 하나를 선택**하게 한 뒤 `settings.json`에 기록. (선택 방식은 ▶ 모델 관리 "모델 선택" 참조)
  - `model <키워드/라벨>` (예: `model opus`, `model 3.1 pro high`) → 등록 목록에서 매칭:
    - **정확히 1개 매칭** → 그 모델로 바로 `settings.json` 기록.
    - **0개 또는 2개 이상 매칭(모호)** → **AskUserQuestion으로 후보를 제시해 하나 선택**하게 한 뒤 기록(임의 결정 금지).
  - `model add ...` 또는 사용자가 **새 모델 목록을 제공**하면 → 이 파일의 "등록된 모델 목록" 섹션을 **갱신(기록)** 한다.
  - `model list` / `model 목록` → 등록된 목록만 출력.
- `$ARGUMENTS` 가 **있고 model이 아니면**:
  - 자연어 작업 지시문이면 → `agy -p "<지시문>"`(비대화형)으로 실행.
  - 이미 `agy`용 옵션 형태면 → 그 의도대로 명령을 구성해 실행.
- `$ARGUMENTS` 가 **없으면**:
  1. 아래 "실행옵션 설명"을 보여준다.
  2. `AskUserQuestion`으로 무엇을 할지 물어본다(단발 질의 / 모델 변경 / 대화형 안내 / 플러그인 / 업데이트).
  3. 선택에 맞춰 실행하거나 안내한다.

---

## ▶ 모델 관리 (직접 수정)

### 등록된 모델 목록 (사용자 제공 — 출처: 본인 `/model` 화면)
- 마지막 갱신: 2026-05-31
- 아래 라벨은 **사용자 계정에서 실제로 보이는 값**이다. 여기 있는 라벨만 사용하고, **임의로 만들거나 추측하지 않는다.**

| 키워드(약칭) | 정확한 라벨(= settings.json에 넣을 값) |
|---|---|
| flash low | `Gemini 3.5 Flash (Low)` |
| flash medium | `Gemini 3.5 Flash (Medium)` |
| flash high | `Gemini 3.5 Flash (High)` |
| pro low | `Gemini 3.1 Pro (Low)` |
| pro high | `Gemini 3.1 Pro (High)` |
| sonnet | `Claude Sonnet 4.6 (Thinking)` |
| opus | `Claude Opus 4.6 (Thinking)` |
| gpt-oss | `GPT-OSS 120B (Medium)` |

- 주의: 모델 목록은 **계정·티어·시점에 따라 달라진다.** 사용자가 새 목록(스크린샷/텍스트)을 제공하면 위 표를 **그 내용으로 교체·갱신**하고 "마지막 갱신" 날짜를 바꾼다.
- 진짜 최신 목록은 항상 대화형 `agy` → `/model` 이 정답임을 사용자에게 상기시킨다.

### 모델 선택 (AskUserQuestion — 정확한 모델 미제공 시)
- 사용자가 **모델을 정확히 지정하지 않았거나**(예: `/agy model`), 입력이 **등록 목록과 정확히 일치하지 않으면**(0개/복수 매칭) → **반드시 `AskUserQuestion`으로 등록된 모델 중 하나를 고르게 한다. 임의로 정하지 않는다.**
- `AskUserQuestion`은 **질문당 옵션 2~4개** 제한이 있다. 등록 모델이 **4개 이하**면 그대로 옵션으로 제시하고, **5개 이상이면 2단계로 나눈다**:
  - 1단계: 계열 선택 — 예) `Gemini Flash` / `Gemini Pro` / `Claude` / `GPT-OSS`
  - 2단계: 세부 선택 — 계열별 변형. 예) Flash → Low/Medium/High, Pro → Low/High, Claude → Sonnet 4.6/Opus 4.6, GPT-OSS → 단일이면 바로 확정(질문 생략).
- 옵션 라벨은 사람이 읽기 쉬운 이름으로 보여주되, 선택 결과는 **등록 표의 "정확한 라벨"로 변환**해 `settings.json`에 기록한다.
- 선택지는 항상 **현재 등록된 목록**을 반영한다(목록이 갱신되면 옵션도 따라 바뀐다). 등록 표에 없는 모델은 옵션에 넣지 않는다.

### 모델 변경 방법 (TUI 없이 파일 편집)
- 대상 파일: `$env:USERPROFILE\.gemini\antigravity-cli\settings.json`
- 그 JSON의 **`"model"` 키 값**을, 위 등록 목록의 **정확한 라벨 문자열로 교체**한다(괄호·대소문자·공백까지 일치). 키가 없으면 추가한다.
- 편집은 JSON 구조를 깨지 않게 한다(다른 키 `trustedWorkspaces` 등은 보존).
- 예시(PowerShell):
  ```powershell
  $p = "$env:USERPROFILE\.gemini\antigravity-cli\settings.json"
  $j = Get-Content $p -Raw | ConvertFrom-Json
  $j.model = "Claude Opus 4.6 (Thinking)"   # ← 등록 목록의 라벨로
  $j | ConvertTo-Json -Depth 10 | Set-Content $p -Encoding utf8
  ```

### 주의·검증 (필수)
- ⚠️ **agy 대화형 세션(TUI)이 떠 있는 동안엔 편집 금지** — 세션 종료 시 메모리값으로 `settings.json`을 덮어써 편집이 날아간다. 비대화형 `-p`는 매번 새로 읽으므로 **호출 직전 편집은 안전**.
- 변경 후 검증: `settings.json`의 `"model"` 값을 다시 읽어 사용자에게 확인시키고,
  필요하면 최신 로그(`$env:USERPROFILE\.gemini\antigravity-cli\log\cli-*.log` 또는 `cli.log`)에서
  `Propagating selected model override to backend: label="..."` 줄로 실제 반영을 확인한다.
- 계정에 없는 라벨을 넣으면 무시·폴백될 수 있으므로, **등록 목록에 없는 값은 쓰지 말고** 사용자에게 `/model`로 확인을 요청한다.

---

## 실행 방법 (환경 제약 — 반드시 준수)
- 실행 바이너리: `& "$env:LOCALAPPDATA\agy\bin\agy.exe"` (PATH 미반영 가능 → **풀경로** 호출).
- Claude의 PowerShell 도구로는 **비대화형 `--print`(`-p`) 모드만** 실행한다.
  - 대화형 TUI(`agy` 단독)·브라우저 로그인은 도구에서 멈추므로 실행하지 말고, 사용자 본인 터미널에서 하도록 안내한다.
- print 모드는 응답이 길 수 있다 → `--print-timeout 120s` 등 지정, 도구 timeout도 넉넉히(예: 180000ms).
- 비대화형 실행은 **현재 `settings.json`에 설정된 모델**을 사용한다(모델 변경은 위 ▶ 모델 관리 참조).

## 실행옵션 설명 (사용자에게 보여줄 내용)

### 실행 모드
- `agy` — 대화형 TUI 세션(사용자 터미널 전용, 첫 실행 시 Google 로그인)
- `agy -p "프롬프트"` / `--print` — 단발 비대화형 실행 후 결과 출력 ★도구로 실행 가능
- `agy -i "프롬프트"` / `--prompt-interactive` — 초기 프롬프트 후 대화 계속
- `--prompt` — `--print` 별칭

### 세션 이어가기 (멀티턴)
- `-c` / `--continue` — 가장 최근 대화 이어가기
- `--conversation <ID>` — 특정 대화 ID로 재개
- 비대화형으로 멀티턴: `agy -p "..."` → `agy -c -p "..."` 반복

### 워크스페이스·실행환경·권한
- `--add-dir <경로>` — 작업공간에 디렉터리 추가(반복 가능)
- `--sandbox` — 터미널 제한 샌드박스(안전) 모드
- `--dangerously-skip-permissions` — ⚠️ 모든 도구 권한 자동승인(위험). **사용자가 명시적으로 요청할 때만**.
- `--print-timeout <시간>` — print 모드 대기 타임아웃(기본 5m0s)
- `--log-file <경로>` — CLI 로그파일 경로 변경

### 서브커맨드
- `agy install` — 환경 경로·셸 설정 (`--dir`, `--skip-aliases`, `--skip-path`)
- `agy update` — CLI 업데이트
- `agy plugin` (= `plugins`) — `list` / `import [gemini|claude]` / `install <target@marketplace>` / `uninstall <name>` / `enable <name>` / `disable <name>` / `validate [path]` / `link <mp> <target>`
- `agy changelog` — 변경사항·릴리스 노트
- `agy help` — 서브커맨드 도움말

### 세션 내 슬래시 명령(대화형, 참고)
- `/model` — 모델 목록·선택 / `/usage`·`/quota` — 쿼터 / `/credits` — G1 크레딧 / `/diff` — 변경 검토 / `/exit` — 종료

## 안전·확인
- 파일을 수정·삭제하거나 외부로 보내는 작업은 실행 전 사용자에게 확인한다(모델 변경은 `settings.json` 1줄 수정이라 바로 진행 가능).
- `--dangerously-skip-permissions`는 기본 사용 금지(요청 시에만).
- 실행한 명령과 결과(요약), 변경한 모델값을 사용자에게 그대로 보고한다.

## 실행 예시
```powershell
# 비대화형 실행(현재 설정 모델 사용)
& "$env:LOCALAPPDATA\agy\bin\agy.exe" -p "이 워크스페이스의 spec 폴더 내용을 한 문단으로 요약" --print-timeout 120s
# 플러그인/버전
& "$env:LOCALAPPDATA\agy\bin\agy.exe" plugin list
& "$env:LOCALAPPDATA\agy\bin\agy.exe" --version
```
