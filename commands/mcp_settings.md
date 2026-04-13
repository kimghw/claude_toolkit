# MCP 서버 설정 가이드

## 사전 준비

```bash
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt-get install -y nodejs
```

- Node.js 20+ 필요
- Claude Code CLI 설치: `sudo npm install -g @anthropic-ai/claude-code`
- 

---

## 1. Codex CLI (OpenAI)

### 설치
```bash
sudo npm install -g @openai/codex
```

### 인증 설정

| 방식 | 명령어 |
|---|---|
| 구독 (ChatGPT Pro/Plus/Team) | `codex login --device-auth` → 브라우저에서 디바이스 코드 입력 |
| API 키 | `export OPENAI_API_KEY="sk-..."` |

### MCP 서버 등록
```bash
claude mcp add --transport stdio codex -- codex mcp-server
```

### 제공 도구

| 도구 | 설명 |
|---|---|
| `codex` | 새 코딩 세션 시작 (prompt 전달) |
| `codex-reply` | 기존 세션에 후속 지시 (threadId로 이어서 대화) |

### 주요 파라미터

| 파라미터 | 설명 | 예시 |
|---|---|---|
| `model` | 모델 선택 | `gpt-5.2`, `gpt-5.2-codex` |
| `prompt` | 초기 프롬프트 (필수) | 자유 텍스트 |
| `approval-policy` | 명령어 실행 승인 정책 | `untrusted`, `on-failure`, `on-request`, `never` |
| `sandbox` | 샌드박스 모드 | `read-only`, `workspace-write`, `danger-full-access` |
| `cwd` | 작업 디렉토리 | 경로 |

---

## 2. Gemini CLI (Google)

### 설치
```bash
sudo npm install -g @google/gemini-cli
```

### 인증 (최초 1회)
```bash
gemini
```

### MCP 서버 등록

Gemini CLI는 자체 MCP 서버 모드가 없으므로 서드파티 래퍼 사용:

```bash
claude mcp add --transport stdio gemini -- npx -y gemini-mcp-tool
```

### 제공 도구

| 도구 | 설명 |
|---|---|
| `ask-gemini` | Gemini에 질문/작업 요청 |
| `brainstorm` | 브레인스토밍 |
| `fetch-chunk` | 대용량 콘텐츠 청크 단위 조회 |

---

## 참고: 설정 파일 직접 편집

`~/.claude/settings.json`을 직접 수정하는 방법:

```json
{
  "mcpServers": {
    "codex": {
      "command": "codex",
      "args": ["mcp-server"]
    },
    "gemini": {
      "command": "npx",
      "args": ["-y", "gemini-mcp-tool"]
    }
  }
}
```
