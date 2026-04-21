---
description: "Codex/Gemini 서브에이전트 설정. 기본은 CLI 설치·인증, 'mcp' 인자 시 MCP 서버 등록, 'update' 인자 시 최신 모델로 재설정."
allowed-tools: Bash, Read, Edit, Write
---

# /set_subAgents 명령 — 서브에이전트(Codex/Gemini) 설정

인자: $ARGUMENTS

## 인자 요약

| 인자 | 동작 |
|------|------|
| (없음) | **기본**: Codex/Gemini CLI 설치 + 인증 (Node.js 20+ 사전 점검 포함). 아래 "CLI 설치 (기본 동작)" 섹션. |
| `mcp` | Claude Code MCP 서버로 Codex/Gemini 등록만 수행. **CLI 설치·인증은 이미 완료됐다고 가정**하며, 미설치 시 먼저 `/set_subAgents` 실행을 안내하고 중단. 아래 "MCP 등록 (옵션)" 섹션. |
| `update` | Codex/Gemini를 아래 "최신 모델 정보" 표의 값으로 재설정. |

## 최신 모델 정보 (단일 출처)

이 섹션의 값이 **"최신 모델"의 정의**이다. 모델이 새로 출시되면 이 표만 수정하면 `/set_subAgents update`가 자동으로 새 값을 적용한다.

| 엔진 | 최신 모델 | 보조 설정 |
|------|-----------|-----------|
| Codex | `gpt-5.4` | `reasoning_effort = "xhigh"` |
| Gemini | `gemini-3.1-pro` | — |

> 값을 갱신할 때는 공식 출처(OpenAI / Google 공지, `codex --help`, `gemini models list` 등)에서 확인 후 위 표를 업데이트하고 본 문서의 다른 예시들도 동일한 값으로 맞춘다.

---

## CLI 설치 (기본 동작)

인자가 없을 때 수행하는 기본 시나리오. **MCP 등록은 하지 않는다.** MCP 연동이 필요하면 이후 `/set_subAgents mcp` 로 별도 호출.

### 0. 사전 준비 — Node.js 20+ 및 Claude Code CLI

1. Node.js 버전 점검:

   ```bash
   node -v
   ```

2. 없거나 20 미만이면 NodeSource 설치 스크립트 실행:

   ```bash
   curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt-get install -y nodejs
   ```

3. Claude Code CLI 점검/설치 (없을 때만):

   ```bash
   command -v claude >/dev/null || sudo npm install -g @anthropic-ai/claude-code
   ```

### 1. Codex CLI (OpenAI)

#### 설치

```bash
sudo npm install -g @openai/codex
```

#### 인증

| 방식 | 명령어 |
|---|---|
| 구독 (ChatGPT Pro/Plus/Team) | `codex login --device-auth` → 브라우저에서 디바이스 코드 입력 |
| API 키 | `export OPENAI_API_KEY="sk-..."` |

#### 설정 파일 (`~/.codex/config.toml`)

CLI 기본값 설정. MCP로 등록하지 않더라도 CLI 호출 시 이 값이 사용된다.

```toml
model = "gpt-5.4"
reasoning_effort = "xhigh"      # low | medium | high | xhigh
```

| 키 | 설명 | 기본값 |
|---|---|---|
| `model` | 사용할 모델 | `o3` |
| `reasoning_effort` | 추론 수준 | `medium` |
| `sandbox_permissions` | 샌드박스 권한 | `[]` |
| `shell_environment_policy.inherit` | 셸 환경변수 상속 | - |

### 2. Gemini CLI (Google)

#### 설치

```bash
sudo npm install -g @google/gemini-cli
```

#### 인증 (최초 1회)

```bash
gemini
```

### 3. 설치 검증

```bash
codex --version
gemini --version
```

두 바이너리가 정상 응답하면 기본 동작 완료. MCP 연동이 필요하면 `/set_subAgents mcp` 를 안내한다.

---

## MCP 등록 (옵션, `mcp` 인자)

사용자가 `/set_subAgents mcp` 로 명시 요청했을 때만 수행한다.

### 사전 조건

- `codex`, `gemini` 바이너리가 PATH 에 있어야 한다. 다음으로 확인:

  ```bash
  command -v codex && command -v gemini
  ```

- 둘 중 하나라도 없으면 **MCP 등록을 중단**하고 사용자에게 다음 안내 후 종료:

  > Codex/Gemini CLI 가 설치돼 있지 않습니다. 먼저 `/set_subAgents` 로 기본 설치를 마친 뒤 `/set_subAgents mcp` 를 다시 실행하세요.

### 1. Codex MCP 등록

```bash
claude mcp add -s user --transport stdio codex -- codex mcp-server
```

`-c` 플래그로 config 값을 인라인 오버라이드할 수 있다 (보통은 `~/.codex/config.toml` 위임 권장):

```bash
claude mcp add -s user --transport stdio codex -- codex mcp-server -c reasoning_effort="xhigh" -c model="gpt-5.4"
```

> `-c` 플래그는 config.toml 값을 오버라이드한다. config.toml에 이미 설정된 값은 별도 지정 없이 MCP 서버에 자동 적용된다.

#### 제공 도구

| 도구 | 설명 |
|---|---|
| `codex` | 새 코딩 세션 시작 (prompt 전달) |
| `codex-reply` | 기존 세션에 후속 지시 (threadId로 이어서 대화) |

#### 주요 파라미터

| 파라미터 | 설명 | 예시 |
|---|---|---|
| `model` | 모델 선택 | `gpt-5.2`, `gpt-5.2-codex` |
| `prompt` | 초기 프롬프트 (필수) | 자유 텍스트 |
| `approval-policy` | 명령어 실행 승인 정책 | `untrusted`, `on-failure`, `on-request`, `never` |
| `sandbox` | 샌드박스 모드 | `read-only`, `workspace-write`, `danger-full-access` |
| `cwd` | 작업 디렉토리 | 경로 |

### 2. Gemini MCP 등록

Gemini CLI 는 자체 MCP 서버 모드가 없으므로 서드파티 래퍼 사용:

```bash
npm install -g gemini-mcp-tool
claude mcp add -s user --transport stdio gemini -- gemini-mcp
```

> 패키지명은 `gemini-mcp-tool` 이지만 실행 바이너리는 `gemini-mcp` 이다.
> Codex 와 달리 등록 시 모델을 고정하지 않고, 도구 호출 시 `model` 파라미터로 선택한다.

#### 제공 도구

| 도구 | 설명 |
|---|---|
| `ask-gemini` | Gemini 에 질문/작업 요청 (`model` 파라미터로 모델 선택) |
| `brainstorm` | 브레인스토밍 (창의적 프레임워크 자동 적용) |
| `fetch-chunk` | 대용량 콘텐츠 청크 단위 조회 |

#### 주요 파라미터 (`ask-gemini`)

| 파라미터 | 설명 | 예시 |
|---|---|---|
| `prompt` | 분석 요청 (필수). `@file` 구문으로 파일 포함 가능 | `@main.py 이 코드 설명해줘` |
| `model` | 모델 선택 (기본: `gemini-2.5-pro`) | **`gemini-3.1-pro`**, `gemini-2.5-flash` |
| `sandbox` | 샌드박스 모드에서 코드 실행 | `true` / `false` |
| `changeMode` | 구조화된 편집 제안 반환 | `true` / `false` |

### 3. 검증

```bash
claude mcp list
```

Codex / Gemini 가 목록에 등록돼 있는지 확인.

---

## update 모드 (`update` 인자)

인자가 `update` 일 때 수행하는 동작. CLI 및/또는 MCP 등록이 이미 돼 있다고 가정하고 **모델 값만** 최신으로 맞춘다.

### 동작 순서

1. **현재 상태 확인**
   - `claude mcp list` 로 등록된 MCP 서버 목록 확인.
   - `~/.codex/config.toml` 존재 여부 및 현재 `model` / `reasoning_effort` 값 읽기.
   - `claude mcp get codex` 와 `claude mcp get gemini` 로 현재 args/env 확인 (있으면).

2. **Codex 갱신**
   - `~/.codex/config.toml` 의 `model` 을 위 표의 Codex 최신 모델로, `reasoning_effort` 를 표의 보조 설정 값으로 설정.
     - 파일이 없으면 `mkdir -p ~/.codex && touch ~/.codex/config.toml` 후 생성.
     - 파일이 있으면 해당 키만 덮어쓰고 나머지 라인은 보존.
   - MCP 등록이 이미 있으면:
     - `-c model=...` / `-c reasoning_effort=...` 가 args 에 **인라인**으로 하드코딩 돼 있는 경우 → 제거 재등록 필요(아래).
     - 인라인 오버라이드 없이 등록돼 있으면 config.toml 갱신만으로 충분. 재등록 불필요.
   - 재등록이 필요한 경우:

     ```bash
     claude mcp remove codex -s user
     claude mcp add -s user --transport stdio codex -- codex mcp-server
     ```

     인라인 오버라이드를 더는 사용하지 않고 config.toml 에 위임.

3. **Gemini 갱신**
   - Gemini 는 등록 시점에 모델을 고정하지 않지만, **`GEMINI_MODEL` 환경변수**나 `ask-gemini` 의 기본 `model` 파라미터로 제어 가능.
   - `claude mcp get gemini` 의 env 에 `GEMINI_MODEL` 이 설정돼 있으면 위 표의 Gemini 최신 모델로 덮어쓰기 위해 재등록:

     ```bash
     claude mcp remove gemini -s user
     GEMINI_MODEL="<표의 Gemini 최신 모델>" claude mcp add -s user --transport stdio gemini --env GEMINI_MODEL="<동일 값>" -- gemini-mcp
     ```

   - `GEMINI_MODEL` 이 설정돼 있지 않았다면 사용자에게 "등록 시 고정하시겠습니까? (기본은 호출 시 `model` 파라미터로 지정)" 확인 후 선택.

4. **검증 및 보고**
   - `claude mcp list` 로 재확인.
   - `cat ~/.codex/config.toml` 로 최종 값 확인.
   - 결과 리포트 형식: `엔진 | 이전 값 → 새 값 | 재등록 여부`.

### 주의

- **재등록은 파괴적**이 아니라 메타데이터만 바꾸지만, `-s user` / `-s project` 스코프가 섞여 있으면 의도치 않은 스코프로 옮겨질 수 있다. 먼저 스코프를 명시 확인한 뒤 동일 스코프로 재등록할 것.
- config.toml 의 **다른 사용자 설정**(예: `sandbox_permissions`, `shell_environment_policy`)은 절대 건드리지 않는다. 해당 키들만 수정.
- 값이 이미 최신과 동일하면 "변경 없음"으로 보고하고 재등록하지 않는다.

---

## 참고: 설정 파일 직접 편집

`~/.claude/settings.json` 을 직접 수정하는 방법:

```json
{
  "mcpServers": {
    "codex": {
      "command": "codex",
      "args": ["mcp-server", "-c", "model=\"gpt-5.4\"", "-c", "reasoning_effort=\"xhigh\""]
    },
    "gemini": {
      "command": "gemini-mcp",
      "args": [],
      "env": {
        "GEMINI_MODEL": "gemini-3.1-pro"
      }
    }
  }
}
```
