"""Claude toolkit exporter — FastAPI service.

Source is fixed at ~/claude_toolkit/.claude. Target is chosen via a server-side
directory browser. Each action reproduces the `.claude/<category>/<item>` layout
at the target (symlink/copy) or inside the ZIP archive.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

SOURCE_ROOT = (Path.home() / "claude_toolkit" / ".claude").resolve()
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
    m = _WIN_DRIVE_RE.match(s)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}".rstrip("/")
    return s.replace("\\", "/")


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


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
