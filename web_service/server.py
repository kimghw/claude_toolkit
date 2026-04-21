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
    if dst.is_symlink() or dst.is_file():
        dst.unlink()
    elif dst.is_dir():
        shutil.rmtree(dst)


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


@app.get("/api/roots")
def get_roots() -> dict:
    roots: list[dict] = [{"label": "Home", "path": str(Path.home())}]
    system = platform.system()
    if system == "Windows":
        for letter in string.ascii_uppercase[2:]:
            drive = Path(f"{letter}:/")
            if drive.exists():
                roots.append({"label": f"{letter}:", "path": f"{letter}:\\"})
    elif _is_wsl():
        for letter in ("c", "d", "e", "f"):
            m = Path(f"/mnt/{letter}")
            if m.exists():
                roots.append({"label": f"/mnt/{letter}", "path": str(m)})
        roots.append({"label": "/", "path": "/"})
    else:
        roots.append({"label": "/", "path": "/"})
    return {"roots": roots}


@app.get("/api/browse")
def browse(path: str = Query(default="")) -> dict:
    base = Path(_normalize_path(path)).expanduser() if path else Path.home()
    p = base.resolve()
    if not p.exists() or not p.is_dir():
        raise HTTPException(400, f"not a directory: {p}")
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

    results = []
    for src, rel in pairs:
        dst = target_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        _remove(dst)
        if req.mode == "symlink":
            dst.symlink_to(src)
            action = "symlink"
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


@app.post("/api/github/export")
def github_export(req: ExportRequest):
    if not req.items:
        raise HTTPException(400, "no items selected")
    nn = _normalize_nn(req.nn)
    pairs = [(_safe_source(rel), rel) for rel in req.items]

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

    uvicorn.run(app, host="127.0.0.1", port=8765)
