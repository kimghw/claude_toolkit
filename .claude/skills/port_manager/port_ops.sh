#!/usr/bin/env bash
# port_ops.sh — port_manager 스킬의 저수준 유틸리티
#
# 사용법:
#   port_ops.sh list <project>                       # 프로젝트의 행 출력 (TSV: 포트\t서비스\t시작명령\t작업디렉토리)
#   port_ops.sh list_all                             # port_list.md 전체 표 출력
#   port_ops.sh has   <project> <port>               # 행 존재 시 exit 0, 없으면 exit 1
#   port_ops.sh add   <project> <port> <service> <cmd> <cwd>   # 행 추가 (존재하면 오류)
#   port_ops.sh update <project> <port> <service> <cmd> <cwd>  # 같은 (project,port) 행 갱신 (없으면 오류)
#   port_ops.sh remove <project> <port>              # 행 삭제 (없으면 NOT_FOUND)
#   port_ops.sh status <port>                        # "RUNNING <pid>" 또는 "STOPPED"
#   port_ops.sh kill <port>                          # 포트의 LISTEN 프로세스 종료. "KILLED <pid>" 또는 "NOT_RUNNING"
#   port_ops.sh start <port> <cwd> <cmd...>          # cwd로 cd 후 cmd를 백그라운드 실행, 로그파일 경로 출력
#   port_ops.sh restart <port> <cwd> <cmd...>        # kill + start
#
# 환경변수:
#   PORT_LIST   port_list.md 경로 (기본: $HOME/claude_toolkit/.claude/references/port_list.md)
#   PROJECT_ROOT  start 시 cwd 기준 루트 (기본: $PWD)
#   LOG_DIR     백그라운드 로그 디렉토리 (기본: /tmp/port_manager)

set -euo pipefail

PORT_LIST="${PORT_LIST:-$HOME/claude_toolkit/.claude/references/port_list.md}"
PROJECT_ROOT="${PROJECT_ROOT:-$PWD}"
LOG_DIR="${LOG_DIR:-/tmp/port_manager}"
mkdir -p "$LOG_DIR"

die() { echo "port_ops: $*" >&2; exit 2; }

list_rows() {
  local project="$1"
  [ -f "$PORT_LIST" ] || die "port_list.md not found: $PORT_LIST"
  awk -F'|' -v proj="$project" '
    /^\|/ {
      f1=$2; gsub(/^[ \t]+|[ \t]+$/,"",f1)
      if (f1 == proj) {
        for (i=2; i<=NF; i++) gsub(/^[ \t]+|[ \t]+$/,"",$i)
        # 출력: 포트\t서비스\t시작명령\t작업디렉토리
        print $3 "\t" $4 "\t" $5 "\t" $6
      }
    }
  ' "$PORT_LIST"
}

list_all_rows() {
  [ -f "$PORT_LIST" ] || die "port_list.md not found: $PORT_LIST"
  cat "$PORT_LIST"
}

ensure_list() {
  if [ ! -f "$PORT_LIST" ]; then
    mkdir -p "$(dirname "$PORT_LIST")"
    {
      echo "# 프로젝트 서버·포트·실행명령 할당"
      echo
      echo "본 표는 \`/port_manager\` 가 읽는 단일 출처(SSOT)다. 한 행 = 한 서버 정의."
      echo
      echo "| 프로젝트 | 포트 | 서비스 | 시작명령 | 작업디렉토리 |"
      echo "|---------|------|-------|---------|------------|"
    } > "$PORT_LIST"
  fi
}

has_row() {
  local project="$1" port="$2"
  [ -f "$PORT_LIST" ] || return 1
  awk -F'|' -v proj="$project" -v p="$port" '
    /^\|/ {
      f1=$2; gsub(/^[ \t]+|[ \t]+$/,"",f1)
      f2=$3; gsub(/^[ \t]+|[ \t]+$/,"",f2)
      if (f1 == proj && f2 == p) { found=1; exit }
    }
    END { exit (found ? 0 : 1) }
  ' "$PORT_LIST"
}

# 셀 안에서 파이프(|)와 백슬래시는 마크다운 표를 깨므로 이스케이프한다.
# (실제 사용에서는 거의 발생하지 않지만 방어용)
sanitize_cell() {
  local v="$1"
  v="${v//\\/\\\\}"
  v="${v//|/\\|}"
  if [ -z "$v" ]; then v="—"; fi
  printf '%s' "$v"
}

cmd_add() {
  local project="$1" port="$2" service="$3" cmd_="$4" cwd_="$5"
  [ -n "$project" ] && [ -n "$port" ] || die "add: project and port required"
  ensure_list
  if has_row "$project" "$port"; then
    die "row already exists: $project:$port (use 'update')"
  fi
  printf '| %s | %s | %s | %s | %s |\n' \
    "$(sanitize_cell "$project")" \
    "$(sanitize_cell "$port")" \
    "$(sanitize_cell "$service")" \
    "$(sanitize_cell "$cmd_")" \
    "$(sanitize_cell "$cwd_")" \
    >> "$PORT_LIST"
  echo "ADDED $project $port"
}

cmd_update() {
  local project="$1" port="$2" service="$3" cmd_="$4" cwd_="$5"
  [ -n "$project" ] && [ -n "$port" ] || die "update: project and port required"
  has_row "$project" "$port" || die "no such row: $project:$port (use 'add')"
  local tmp; tmp="$(mktemp)"
  awk -F'|' -v proj="$project" -v p="$port" \
      -v s="$(sanitize_cell "$service")" \
      -v c="$(sanitize_cell "$cmd_")" \
      -v w="$(sanitize_cell "$cwd_")" '
    /^\|/ {
      f1=$2; gsub(/^[ \t]+|[ \t]+$/,"",f1)
      f2=$3; gsub(/^[ \t]+|[ \t]+$/,"",f2)
      if (f1 == proj && f2 == p) {
        printf "| %s | %s | %s | %s | %s |\n", proj, p, s, c, w
        next
      }
    }
    { print }
  ' "$PORT_LIST" > "$tmp" && mv "$tmp" "$PORT_LIST"
  echo "UPDATED $project $port"
}

cmd_remove() {
  local project="$1" port="$2"
  [ -n "$project" ] && [ -n "$port" ] || die "remove: project and port required"
  if ! has_row "$project" "$port"; then
    echo "NOT_FOUND $project $port"; return 0
  fi
  local tmp; tmp="$(mktemp)"
  awk -F'|' -v proj="$project" -v p="$port" '
    /^\|/ {
      f1=$2; gsub(/^[ \t]+|[ \t]+$/,"",f1)
      f2=$3; gsub(/^[ \t]+|[ \t]+$/,"",f2)
      if (f1 == proj && f2 == p) next
    }
    { print }
  ' "$PORT_LIST" > "$tmp" && mv "$tmp" "$PORT_LIST"
  echo "REMOVED $project $port"
}

find_pid() {
  local port="$1" pid=""
  if command -v ss >/dev/null 2>&1; then
    pid="$(ss -tlnpH "sport = :$port" 2>/dev/null \
      | grep -oP 'pid=\K[0-9]+' | head -1 || true)"
  fi
  if [ -z "$pid" ] && command -v lsof >/dev/null 2>&1; then
    pid="$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
  fi
  if [ -z "$pid" ] && command -v fuser >/dev/null 2>&1; then
    pid="$(fuser -n tcp "$port" 2>/dev/null | tr -s ' \t' '\n' | grep -E '^[0-9]+$' | head -1 || true)"
  fi
  printf '%s' "$pid"
}

cmd_status() {
  local port="$1"
  local pid; pid="$(find_pid "$port")"
  if [ -n "$pid" ]; then
    echo "RUNNING $pid"
  else
    echo "STOPPED"
  fi
}

cmd_kill() {
  local port="$1"
  local pid; pid="$(find_pid "$port")"
  if [ -z "$pid" ]; then
    echo "NOT_RUNNING"
    return 0
  fi
  kill "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    sleep 0.4
    [ -z "$(find_pid "$port")" ] && { echo "KILLED $pid"; return 0; }
  done
  kill -9 "$pid" 2>/dev/null || true
  sleep 0.4
  if [ -z "$(find_pid "$port")" ]; then
    echo "KILLED $pid"
  else
    echo "KILL_FAILED $pid"
    return 1
  fi
}

cmd_start() {
  local port="$1"; shift
  local cwd_rel="$1"; shift
  local cmd=("$@")
  local cwd
  if [ "$cwd_rel" = "—" ] || [ -z "$cwd_rel" ]; then
    cwd="$PROJECT_ROOT"
  elif [[ "$cwd_rel" = /* ]]; then
    cwd="$cwd_rel"
  else
    cwd="$PROJECT_ROOT/$cwd_rel"
  fi
  [ -d "$cwd" ] || die "cwd not found: $cwd"
  local proj_slug; proj_slug="$(basename "$PROJECT_ROOT" | tr -c 'A-Za-z0-9_-' '_')"
  local log="$LOG_DIR/${proj_slug}-${port}.log"
  : > "$log"
  ( cd "$cwd" && nohup bash -lc "${cmd[*]}" >>"$log" 2>&1 & echo $! >"$LOG_DIR/${proj_slug}-${port}.pid" ) &
  wait
  local launched_pid; launched_pid="$(cat "$LOG_DIR/${proj_slug}-${port}.pid" 2>/dev/null || true)"
  echo "STARTED pid=${launched_pid:-?} log=$log"
}

cmd_restart() {
  local port="$1"; shift
  local cwd_rel="$1"; shift
  local cmd=("$@")
  cmd_kill "$port" || true
  cmd_start "$port" "$cwd_rel" "${cmd[@]}"
}

main() {
  local sub="${1:-}"; shift || true
  case "$sub" in
    list)     [ $# -ge 1 ] || die "usage: list <project>";     list_rows "$1" ;;
    list_all) list_all_rows ;;
    has)      [ $# -ge 2 ] || die "usage: has <project> <port>";    has_row "$1" "$2" && echo "YES" || { echo "NO"; exit 1; } ;;
    add)      [ $# -ge 5 ] || die "usage: add <project> <port> <service> <cmd> <cwd>";    cmd_add "$@" ;;
    update)   [ $# -ge 5 ] || die "usage: update <project> <port> <service> <cmd> <cwd>"; cmd_update "$@" ;;
    remove)   [ $# -ge 2 ] || die "usage: remove <project> <port>";  cmd_remove "$@" ;;
    status)   [ $# -ge 1 ] || die "usage: status <port>";      cmd_status "$1" ;;
    kill)     [ $# -ge 1 ] || die "usage: kill <port>";        cmd_kill "$1" ;;
    start)    [ $# -ge 3 ] || die "usage: start <port> <cwd> <cmd...>";   cmd_start "$@" ;;
    restart)  [ $# -ge 3 ] || die "usage: restart <port> <cwd> <cmd...>"; cmd_restart "$@" ;;
    ""|help|-h|--help)
      awk 'NR==1 {next} /^#/ || /^[[:space:]]*$/ {print; next} {exit}' "$0"
      ;;
    *) die "unknown subcommand: $sub" ;;
  esac
}

main "$@"
