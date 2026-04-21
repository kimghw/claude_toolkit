"""Claude toolkit exporter — FastAPI service.

Source is fixed at ~/claude_toolkit/.claude. Target is chosen via a server-side
directory browser. Each action reproduces the `.claude/<category>/<item>` layout
at the target (symlink/copy) or inside the ZIP archive.
"""

from __future__ import annotations

import io
import os
import platform
import re
import shutil
import stat as _stat
import string
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel


def _is_wsl() -> bool:
    # WSL reports Linux but embeds "microsoft" in /proc/version.
    if platform.system() != "Linux":
        return False
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


_WSL_MNT_DRIVE_RE = re.compile(r"^/mnt/[a-zA-Z](/|$)")


def _is_windows_fs_target(dst: Path) -> bool:
    """대상 경로가 Windows 파일시스템(NTFS)을 향하는지 판정.

    symlink 모드는 POSIX/WSL 네이티브 경로에서만 허용한다.
    Windows 파일시스템(Windows 네이티브 전체, WSL의 /mnt/<drive>/...)
    에서는 symlink를 만들 수 없게 차단하기 위한 헬퍼.
    """
    if platform.system() == "Windows":
        return True
    if _is_wsl():
        try:
            resolved = str(dst.resolve())
        except (OSError, RuntimeError):
            resolved = str(dst)
        return bool(_WSL_MNT_DRIVE_RE.match(resolved))
    return False


def _resolve_source_root() -> Path:
    env = os.environ.get("CLAUDE_TOOLKIT_ROOT")
    if env:
        p = Path(env).expanduser().resolve()
        if p.name != ".claude":
            p = p / ".claude"
    else:
        p = (Path(__file__).resolve().parents[1] / ".claude").resolve()
    if not p.exists():
        raise RuntimeError(f"SOURCE_ROOT does not exist: {p}")
    return p


SOURCE_ROOT = _resolve_source_root()
CATEGORIES = ["skills", "agents", "commands", "references"]
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Claude Toolkit Exporter")


class ActionRequest(BaseModel):
    items: List[str]  # category-relative, e.g. "skills/md2wu" or "commands/git.md"
    target: Optional[str] = None  # absolute path to target project root
    mode: Literal["symlink", "copy", "zip"]


def _safe_source(rel: str) -> Path:
    """Resolve a category-relative path under SOURCE_ROOT, rejecting traversal."""
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        raise HTTPException(400, f"invalid item: {rel}")
    src = (SOURCE_ROOT / rel).resolve()
    try:
        src.relative_to(SOURCE_ROOT)
    except ValueError:
        raise HTTPException(400, f"path traversal: {rel}")
    if not src.exists():
        raise HTTPException(404, f"not found: {rel}")
    return src


_WIN_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")


def _normalize_path(raw: str) -> str:
    """Translate Windows-style paths (C:\\foo\\bar) to WSL mounts (/mnt/c/foo/bar)."""
    if not raw:
        return raw
    s = raw.strip().strip('"').strip("'")
    if _is_wsl():
        m = _WIN_DRIVE_RE.match(s)
        if m:
            drive = m.group(1).lower()
            rest = m.group(2).replace("\\", "/")
            return f"/mnt/{drive}/{rest}".rstrip("/")
        return s.replace("\\", "/")
    return s


def _safe_target(target: str) -> Path:
    """Resolve an absolute target path and forbid writing into SOURCE_ROOT itself."""
    if not target:
        raise HTTPException(400, "target required")
    t = Path(_normalize_path(target)).expanduser().resolve()
    if t == SOURCE_ROOT or SOURCE_ROOT in t.parents:
        raise HTTPException(400, "target must be outside source root")
    return t


def _remove(dst: Path) -> None:
    """Remove dst if it exists. Safely handles:
    - POSIX symlinks / NTFS symlinks / NTFS junctions (unlink the link only)
    - WSL LX_SYMLINK reparse points on /mnt/c (stat() fails with WinError 1920)
    - Regular files and directories
    """
    try:
        st = os.lstat(dst)
    except FileNotFoundError:
        return
    except OSError:
        # Reparse point we cannot stat at all (e.g., dangling WSL LX_SYMLINK).
        # Best-effort removal — try both unlink and rmdir.
        for fn in (os.unlink, os.rmdir):
            try:
                fn(dst)
                return
            except OSError:
                continue
        return

    is_reparse = False
    if platform.system() == "Windows":
        attrs = getattr(st, "st_file_attributes", 0)
        is_reparse = bool(attrs & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT

    if _stat.S_ISDIR(st.st_mode):
        # Directory: if it's a junction/symlink, unlink the link; else recurse.
        if is_reparse:
            os.rmdir(dst)
        else:
            shutil.rmtree(dst)
    else:
        os.unlink(dst)


def _create_link(src: Path, dst: Path) -> str:
    """Create a POSIX symlink dst → src.

    정책: symlink 모드는 WSL 네이티브/Linux 경로에서만 허용한다.
    Windows 파일시스템(Windows 네이티브, WSL의 /mnt/<drive>/...)에
    대한 호출은 apply() 단계에서 이미 차단되지만, 방어적으로 한 번 더 막는다.
    """
    if _is_windows_fs_target(dst):
        raise HTTPException(
            400,
            f"symlink mode is not allowed on Windows filesystem: {dst}",
        )
    os.symlink(src, dst)
    return "symlink"


@app.get("/api/tree")
def get_tree() -> dict:
    tree: dict[str, list[dict]] = {}
    for cat in CATEGORIES:
        cat_path = SOURCE_ROOT / cat
        if not cat_path.exists():
            tree[cat] = []
            continue
        entries = []
        for e in sorted(cat_path.iterdir(), key=lambda p: p.name.lower()):
            entries.append(
                {
                    "name": e.name,
                    "type": "dir" if e.is_dir() else "file",
                    "rel": f"{cat}/{e.name}",
                }
            )
        tree[cat] = entries
    return {"source": str(SOURCE_ROOT), "categories": tree}


def _roots_entries() -> list[dict]:
    """SSOT: label/path 쌍 리스트. get_roots() 와 _allowed_roots() 가 공유."""
    entries: list[dict] = [{"label": "Home", "path": str(Path.home())}]
    system = platform.system()
    if system == "Windows":
        for letter in string.ascii_uppercase[2:]:
            drive = Path(f"{letter}:/")
            if drive.exists():
                entries.append({"label": f"{letter}:", "path": f"{letter}:\\"})
    elif _is_wsl():
        for letter in ("c", "d", "e", "f"):
            m = Path(f"/mnt/{letter}")
            if m.exists():
                entries.append({"label": f"/mnt/{letter}", "path": str(m)})
        entries.append({"label": "/", "path": "/"})
    else:
        entries.append({"label": "/", "path": "/"})
    return entries


def _allowed_roots() -> list[Path]:
    """browse() 가 노출을 허용하는 루트 경로 목록."""
    return [Path(_normalize_path(e["path"])) for e in _roots_entries()]


@app.get("/api/roots")
def get_roots() -> dict:
    return {"roots": _roots_entries()}


@app.get("/api/browse")
def browse(path: str = Query(default="")) -> dict:
    base = Path(_normalize_path(path)).expanduser() if path else Path.home()
    p = base.resolve()
    if not p.exists() or not p.is_dir():
        raise HTTPException(400, f"not a directory: {p}")
    roots = [Path(r).expanduser().resolve() for r in _allowed_roots()]
    if not any(p == r or r in p.parents for r in roots):
        raise HTTPException(400, f"path not under allowed roots: {p}")
    dirs = []
    try:
        entries = sorted(p.iterdir(), key=lambda x: x.name.lower())
    except PermissionError:
        entries = []
    for e in entries:
        if e.name.startswith("."):
            continue
        try:
            if e.is_dir():
                dirs.append({"name": e.name, "path": str(e)})
        except (PermissionError, OSError):
            continue
    parent = str(p.parent) if p.parent != p else None
    return {"path": str(p), "parent": parent, "dirs": dirs}


@app.post("/api/apply")
def apply(req: ActionRequest):
    if not req.items:
        raise HTTPException(400, "no items selected")
    pairs = [(_safe_source(rel), rel) for rel in req.items]

    if req.mode == "zip":
        return _build_zip(pairs)

    target_root = _safe_target(req.target or "") / ".claude"
    target_root.mkdir(parents=True, exist_ok=True)

    if req.mode == "symlink" and _is_windows_fs_target(target_root):
        raise HTTPException(
            400,
            (
                "symlink 모드는 Windows 파일시스템에 사용할 수 없습니다 "
                f"(대상: {target_root}). "
                "copy 모드로 다시 시도하거나, WSL 네이티브 경로"
                "(예: ~/project, /home/<user>/...)를 대상으로 지정하세요."
            ),
        )

    results = []
    target_root_resolved = target_root.resolve()
    for src, rel in pairs:
        dst = target_root / rel

        # Symlink traversal guard: reject any parent chain within target_root
        # that is itself a symlink, and verify existing parents resolve under
        # target_root. Also validate dst itself if it already exists.
        for parent in list(dst.parents):
            try:
                parent.relative_to(target_root)
            except ValueError:
                break  # above target_root — stop walking upward
            if parent.is_symlink():
                raise HTTPException(400, f"unsafe target path: {dst}")
            if parent.exists():
                try:
                    parent.resolve().relative_to(target_root_resolved)
                except ValueError:
                    raise HTTPException(400, f"unsafe target path: {dst}")
        if dst.exists() or dst.is_symlink():
            try:
                dst.resolve().relative_to(target_root_resolved)
            except ValueError:
                raise HTTPException(400, f"unsafe target path: {dst}")

        dst.parent.mkdir(parents=True, exist_ok=True)
        _remove(dst)
        if req.mode == "symlink":
            action = _create_link(src, dst)
        else:  # copy
            if src.is_dir():
                shutil.copytree(src, dst, symlinks=False)
            else:
                shutil.copy2(src, dst)
            action = "copy"
        results.append({"rel": rel, "dst": str(dst), "action": action})
    return {"target": str(target_root), "results": results}


def _build_zip(pairs):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, rel in pairs:
            arc_base = f".claude/{rel}"
            if src.is_file():
                zf.write(src, arc_base)
            else:
                for root, _dirs, files in os.walk(src):
                    for f in files:
                        fp = Path(root) / f
                        arcname = f"{arc_base}/{fp.relative_to(src).as_posix()}"
                        zf.write(fp, arcname)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="claude_bundle.zip"'},
    )


_NN_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ExportRequest(BaseModel):
    nn: str
    visibility: Literal["public", "private"] = "public"
    items: List[str]


def _sh(cmd: list[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def _normalize_nn(raw: str) -> str:
    nn = raw.strip()
    if nn.startswith("shared_skills_"):
        nn = nn[len("shared_skills_"):]
    if not _NN_RE.match(nn):
        raise HTTPException(400, f"invalid NN: {raw!r} (allowed: A-Z a-z 0-9 _ -)")
    return nn


def _contains_external_symlink(src: Path) -> Optional[Path]:
    """SOURCE_ROOT 밖을 가리키는 심볼릭 링크가 src 내부에 있으면 그 경로 반환."""
    if src.is_symlink():
        resolved = src.resolve()
        if SOURCE_ROOT not in resolved.parents and resolved != SOURCE_ROOT:
            return src
    if src.is_dir():
        for root, dirs, files in os.walk(src, followlinks=False):
            for name in list(dirs) + list(files):
                p = Path(root) / name
                if p.is_symlink():
                    target = p.resolve()
                    try:
                        target.relative_to(SOURCE_ROOT)
                    except ValueError:
                        return p
    return None


@app.post("/api/github/export")
def github_export(req: ExportRequest):
    if not req.items:
        raise HTTPException(400, "no items selected")
    nn = _normalize_nn(req.nn)
    pairs = [(_safe_source(rel), rel) for rel in req.items]

    for src, _rel in pairs:
        bad = _contains_external_symlink(src)
        if bad is not None:
            raise HTTPException(400, f"source contains external symlink: {bad}")

    auth = _sh(["gh", "auth", "status"])
    if auth.returncode != 0:
        raise HTTPException(
            500,
            "gh not authenticated. Run `gh auth login` in terminal.\n" + auth.stderr,
        )

    who = _sh(["gh", "api", "user", "-q", ".login"])
    if who.returncode != 0 or not who.stdout.strip():
        raise HTTPException(500, f"failed to resolve gh user: {who.stderr}")
    owner = who.stdout.strip()

    scratch = Path(tempfile.gettempdir()) / "export_bundle" / f"shared_skills_{nn}"
    if scratch.exists():
        shutil.rmtree(scratch)
    (scratch / ".claude").mkdir(parents=True)

    for src, rel in pairs:
        dst = scratch / ".claude" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, symlinks=False)
        else:
            shutil.copy2(src, dst)

    stray_links: list[str] = []
    for root, _dirs, files in os.walk(scratch):
        for name in files:
            p = Path(root) / name
            if p.is_symlink():
                stray_links.append(str(p.relative_to(scratch)))

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    paths_md = "\n".join(f"- `.claude/{rel}`" for rel in req.items)
    readme = (
        f"# shared_skills_{nn}\n\n"
        f"Snapshot of selected items from `claude_toolkit`.\n\n"
        f"- Exported: {ts}\n"
        f"- Owner: {owner}\n\n"
        f"## Paths\n\n{paths_md}\n\n"
        f"## Usage\n\n"
        f"```\n"
        f"git clone https://github.com/{owner}/shared_skills_{nn}.git\n"
        f"# then symlink each into your project's .claude/\n"
        f"```\n\n"
        f"This is a force-pushed snapshot; history is not preserved.\n"
    )
    (scratch / "README.md").write_text(readme, encoding="utf-8")

    init = _sh(["git", "init", "-b", "main"], cwd=scratch)
    if init.returncode != 0:
        raise HTTPException(500, f"git init failed: {init.stderr}")
    _sh(["git", "add", "-A"], cwd=scratch)
    commit = _sh(
        ["git", "commit", "-m", f"snapshot: shared_skills_{nn} @ {ts}"], cwd=scratch
    )
    if commit.returncode != 0:
        raise HTTPException(500, f"git commit failed: {commit.stderr or commit.stdout}")

    repo_full = f"{owner}/shared_skills_{nn}"
    exists = _sh(["gh", "repo", "view", repo_full]).returncode == 0

    if exists:
        _sh(
            ["git", "remote", "add", "origin", f"https://github.com/{repo_full}.git"],
            cwd=scratch,
        )
        push = _sh(["git", "push", "-f", "origin", "main"], cwd=scratch)
        if push.returncode != 0:
            raise HTTPException(500, f"push failed: {push.stderr or push.stdout}")
        mode = "update"
    else:
        create = _sh(
            [
                "gh", "repo", "create", repo_full,
                f"--{req.visibility}",
                "--source", str(scratch),
                "--push",
            ]
        )
        if create.returncode != 0:
            raise HTTPException(500, f"repo create failed: {create.stderr or create.stdout}")
        mode = "create"

    return {
        "url": f"https://github.com/{repo_full}",
        "repo": repo_full,
        "mode": mode,
        "items": req.items,
        "stray_symlinks": stray_links,
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    uvicorn.run(app, host=host, port=port)
