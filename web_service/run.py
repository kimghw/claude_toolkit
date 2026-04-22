"""Cross-platform launcher for the Claude Toolkit web service.

Usage:
    python run.py               # foreground on default port 8765
    python run.py 9000          # foreground on port 9000
    python run.py bg            # background (writes .server.pid / .server.log)
    python run.py bg 9000       # background on port 9000
    python run.py stop          # stop the background process
    python run.py status        # show current state

Environment:
    CLAUDE_TOOLKIT_NO_VENV=1    # skip venv creation, install into system python
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PID_FILE = HERE / ".server.pid"
LOG_FILE = HERE / ".server.log"
REQ_FILE = HERE / "requirements.txt"
VENV_DIR = HERE / ".venv"
DEFAULT_PORT = 8765
IS_WIN = platform.system() == "Windows"
NO_VENV = os.environ.get("CLAUDE_TOOLKIT_NO_VENV") == "1"


def _venv_python() -> Path:
    if IS_WIN:
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _resolve_python() -> Path:
    """Return the python executable to use for uvicorn."""
    if NO_VENV:
        return Path(sys.executable)

    py = _venv_python()
    if not py.exists():
        print(f"[run] creating venv at {VENV_DIR}", flush=True)
        subprocess.check_call([sys.executable, "-m", "venv", str(VENV_DIR)])

    try:
        subprocess.check_call(
            [str(py), "-c", "import fastapi, uvicorn"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        print(f"[run] installing deps from {REQ_FILE}", flush=True)
        subprocess.check_call(
            [str(py), "-m", "pip", "install", "-q", "-r", str(REQ_FILE)]
        )
    return py


def _port_busy(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WIN:
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True,
        )
        return str(pid) in r.stdout
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def _handshake(port: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except ValueError:
        return None


def cmd_start(port: int, background: bool) -> int:
    if _port_busy(port):
        print(f"[run] port {port} is already in use", file=sys.stderr)
        return 1

    existing = _read_pid()
    if existing and _pid_alive(existing):
        print(f"[run] already running (pid={existing}). Use `stop` first.")
        return 1

    py = _resolve_python()
    cmd = [
        str(py),
        "-m",
        "uvicorn",
        "server:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]

    if not background:
        os.chdir(HERE)
        print(f"[run] foreground: {' '.join(cmd)}", flush=True)
        os.execv(str(py), cmd)
        return 0  # unreachable

    # background
    log_fh = open(LOG_FILE, "ab")
    popen_kwargs: dict = dict(
        cwd=str(HERE),
        stdout=log_fh,
        stderr=log_fh,
        stdin=subprocess.DEVNULL,
    )
    if IS_WIN:
        DETACHED_PROCESS = 0x00000008
        popen_kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
        )
    else:
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **popen_kwargs)
    PID_FILE.write_text(str(proc.pid))

    if _handshake(port, timeout=5.0):
        print(f"[run] started pid={proc.pid} port={port} log={LOG_FILE}")
        return 0

    print(
        f"[run] started pid={proc.pid} but handshake failed within 5s. "
        f"Check {LOG_FILE}.",
        file=sys.stderr,
    )
    return 2


def cmd_stop() -> int:
    pid = _read_pid()
    if pid is None:
        print("[run] no pid file — nothing to stop")
        return 0
    if not _pid_alive(pid):
        print(f"[run] pid {pid} not alive; clearing pid file")
        PID_FILE.unlink(missing_ok=True)
        return 0

    if IS_WIN:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F", "/T"],
            capture_output=True,
        )
    else:
        import signal

        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(10):
            if not _pid_alive(pid):
                break
            time.sleep(0.5)
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    PID_FILE.unlink(missing_ok=True)
    print(f"[run] stopped pid={pid}")
    return 0


def cmd_status() -> int:
    pid = _read_pid()
    if pid is None:
        print("[run] not running (no pid file)")
        return 0
    alive = _pid_alive(pid)
    port_guess = DEFAULT_PORT
    busy = _port_busy(port_guess)
    print(f"[run] pid={pid} alive={alive} port_{port_guess}_busy={busy}")
    if LOG_FILE.exists():
        print(f"[run] log tail ({LOG_FILE}):")
        lines = LOG_FILE.read_text(errors="replace").splitlines()[-10:]
        for ln in lines:
            print(f"  {ln}")
    return 0


def _parse_action(argv: list[str]) -> tuple[str, int, bool]:
    """Parse legacy-style argv supporting: <empty>, <port>, bg [port], stop, status."""
    action = "start"
    port = DEFAULT_PORT
    background = False

    if not argv:
        return action, port, background

    head = argv[0]
    rest = argv[1:]

    if head.isdigit():
        port = int(head)
        return action, port, background
    if head in ("bg", "background"):
        background = True
        if rest and rest[0].isdigit():
            port = int(rest[0])
        return action, port, background
    if head in ("stop", "status"):
        return head, port, background

    # fall through to argparse for explicit flags
    parser = argparse.ArgumentParser(prog="run.py", add_help=True)
    parser.add_argument("action", nargs="?", default="start",
                        choices=("start", "stop", "status"))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--bg", action="store_true")
    ns = parser.parse_args(argv)
    return ns.action, ns.port, ns.bg


def main() -> int:
    if not (HERE / "server.py").exists():
        print(f"[run] server.py not found next to run.py ({HERE})", file=sys.stderr)
        return 2

    action, port, background = _parse_action(sys.argv[1:])

    if action == "start":
        return cmd_start(port, background)
    if action == "stop":
        return cmd_stop()
    if action == "status":
        return cmd_status()
    print(f"[run] unknown action: {action}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
