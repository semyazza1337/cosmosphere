"""Fetch + parse arxiv astro-ph.HE RSS feed into Paper models."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone

import feedparser

from .models import Paper

ARXIV_FEED_URL = "https://export.arxiv.org/rss/astro-ph.HE"

_ID_RE = re.compile(r"(\d{4}\.\d{4,6})")

logger = logging.getLogger(__name__)


class FetchError(RuntimeError):
    """Raised when the feed cannot be retrieved or parsed."""


def _extract_arxiv_id(entry) -> str | None:
    for field in ("id", "guid", "link"):
        val = entry.get(field)
        if not val:
            continue
        m = _ID_RE.search(val)
        if m:
            return m.group(1)
    return None


def _extract_authors(entry) -> list[str]:
    if "authors" in entry and entry.authors:
        return [a.get("name", "").strip() for a in entry.authors if a.get("name")]
    author = entry.get("author", "")
    if author:
        return [a.strip() for a in author.split(",") if a.strip()]
    return []


def _extract_categories(entry) -> list[str]:
    tags = entry.get("tags") or []
    cats = [t.get("term", "").strip() for t in tags if t.get("term")]
    return [c for c in cats if c]


def _extract_published(entry) -> date:
    for field in ("published_parsed", "updated_parsed"):
        t = entry.get(field)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc).date()
    return date.today()


def _strip_summary(raw: str) -> str:
    """arxiv RSS wraps abstracts in <p>Abstract: ...</p>; normalise."""
    txt = re.sub(r"<[^>]+>", " ", raw or "")
    txt = re.sub(r"\s+", " ", txt).strip()
    if txt.lower().startswith("abstract:"):
        txt = txt[len("abstract:"):].strip()
    return txt


def fetch_papers(seen: set[str], feed_url: str = ARXIV_FEED_URL) -> list[Paper]:
    """Fetch the astro-ph.HE RSS feed and return papers NOT in `seen`.

    Raises FetchError on network failure or unparseable feed.
    """
    logger.info("Fetching %s", feed_url)
    parsed = feedparser.parse(feed_url)

    if parsed.bozo and not parsed.entries:
        raise FetchError(f"Failed to parse feed: {parsed.bozo_exception!r}")
    if not parsed.entries:
        raise FetchError("Feed returned zero entries (arxiv may be down)")

    papers: list[Paper] = []
    for entry in parsed.entries:
        arxiv_id = _extract_arxiv_id(entry)
        if not arxiv_id or arxiv_id in seen:
            continue
        try:
            paper = Paper(
                arxiv_id=arxiv_id,
                title=re.sub(r"\s+", " ", entry.get("title", "").strip()),
                authors=_extract_authors(entry),
                summary=_strip_summary(entry.get("summary", "")),
                categories=_extract_categories(entry),
                published=_extract_published(entry),
                link=entry.get("link") or f"https://arxiv.org/abs/{arxiv_id}",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Skipping malformed entry %s: %s", arxiv_id, e)
            continue
        papers.append(paper)

    logger.info("Fetched %d new papers (%d total in feed)", len(papers), len(parsed.entries))
    return papers
