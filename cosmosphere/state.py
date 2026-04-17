"""Persistent set of already-seen arxiv IDs stored at data/seen.json."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def load_seen(path: Path) -> set[str]:
    """Load seen arxiv IDs. Returns empty set if missing or malformed."""
    if not path.exists():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return set(raw.get("seen", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen(path: Path, seen: set[str]) -> None:
    """Atomically write the seen set so a crash never corrupts state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"seen": sorted(seen)}
    fd, tmp_path = tempfile.mkstemp(
        prefix=".seen-", suffix=".json.tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise
