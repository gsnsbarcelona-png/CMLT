"""Version desplegada (commit) y comprobacion contra el ultimo commit de GitHub.

En Render el commit llega en RENDER_GIT_COMMIT (y el repo/rama en
RENDER_GIT_REPO_SLUG / RENDER_GIT_BRANCH). En local se lee de git; si no hay
git, queda "dev". La comparacion con GitHub es best-effort y cacheada."""

import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter

DEFAULT_REPO = "gsnsbarcelona-png/CMLT"
DEFAULT_BRANCH = "master"
LATEST_CACHE_TTL_SECONDS = 300

STARTED_AT = datetime.now(timezone.utc)
_latest_cache: dict = {"at": 0.0, "value": None}

router = APIRouter(prefix="/api", tags=["version"])


def current_commit() -> str | None:
    env = os.environ.get("RENDER_GIT_COMMIT")
    if env:
        return env
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            timeout=3,
        )
        return out.stdout.strip() or None if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def latest_commit() -> str | None:
    now = time.time()
    if now - _latest_cache["at"] < LATEST_CACHE_TTL_SECONDS:
        return _latest_cache["value"]
    repo = os.environ.get("RENDER_GIT_REPO_SLUG", DEFAULT_REPO)
    branch = os.environ.get("RENDER_GIT_BRANCH", DEFAULT_BRANCH)
    value = None
    try:
        res = httpx.get(
            f"https://api.github.com/repos/{repo}/commits/{branch}",
            headers={"Accept": "application/vnd.github+json"},
            timeout=3.0,
        )
        if res.status_code == 200:
            value = res.json().get("sha")
    except (httpx.HTTPError, ValueError):
        value = None
    _latest_cache.update(at=now, value=value)
    return value


@router.get("/version")
def get_version() -> dict:
    current = current_commit()
    latest = latest_commit()
    return {
        "commit": current[:7] if current else "dev",
        "latest": latest[:7] if latest else None,
        "up_to_date": (current == latest) if current and latest else None,
        "started_at": STARTED_AT.isoformat(),
    }
