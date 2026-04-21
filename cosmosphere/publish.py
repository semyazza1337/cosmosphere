"""Publish markdown artefacts to the Quartz blog repo via git."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_BLOG_REPO = "/home/weck/src/quartz-blog"
GIT_TIMEOUT = 60


class PublishError(RuntimeError):
    """Raised when copy or git push fails."""


def _blog_repo() -> Path:
    return Path(os.environ.get("BLOG_REPO_PATH", DEFAULT_BLOG_REPO)).expanduser()


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    logger.info("git %s", " ".join(args))
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise PublishError(f"git {args[0]} failed to launch: {e}") from e

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise PublishError(f"git {args[0]} exited {result.returncode}: {detail}")
    return result


def publish_to_blog(src: Path, subdir: str, commit_msg: str) -> Path:
    """Copy `src` into `{BLOG_REPO_PATH}/content/{subdir}/` and git push.

    Returns the destination path.
    """
    if not src.exists():
        raise PublishError(f"Source file does not exist: {src}")

    repo = _blog_repo()
    if not (repo / ".git").is_dir():
        raise PublishError(f"Blog repo not a git dir: {repo}")

    dest_dir = repo / "content" / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name

    shutil.copy2(src, dest)
    logger.info("Copied %s -> %s", src, dest)

    _run_git(["add", "."], cwd=repo)

    status = _run_git(["status", "--porcelain"], cwd=repo)
    if not status.stdout.strip():
        logger.info("No changes to commit; skipping push")
        return dest

    _run_git(["commit", "-m", commit_msg], cwd=repo)
    _run_git(["push"], cwd=repo)
    return dest
