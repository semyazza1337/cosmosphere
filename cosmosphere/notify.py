"""Desktop notifications via notify-send. Silent no-op if unavailable."""

from __future__ import annotations

import logging
import shutil
import subprocess

from .models import ScoredPaper

logger = logging.getLogger(__name__)

NOTIFY_THRESHOLD = 9
TITLE_TRUNC = 80


def maybe_notify(papers: list[ScoredPaper], threshold: int = NOTIFY_THRESHOLD) -> int:
    """Fire a desktop notification for each paper scoring >= threshold.

    Returns number of notifications sent. Never raises.
    """
    notify_bin = shutil.which("notify-send")
    if not notify_bin:
        logger.debug("notify-send not on PATH, skipping notifications")
        return 0

    sent = 0
    for p in papers:
        if p.relevance_score < threshold:
            continue
        title = p.title[:TITLE_TRUNC]
        body = f"{p.relevance_score}/10: {title}"
        try:
            subprocess.run(
                [notify_bin, "cosmosphere", body],
                check=False,
                timeout=5,
            )
            sent += 1
        except (OSError, subprocess.TimeoutExpired) as e:
            logger.warning("notify-send failed for %s: %s", p.arxiv_id, e)

    if sent:
        logger.info("Sent %d desktop notification(s)", sent)
    return sent
