"""NASA Astronomy Picture of the Day fetcher (stdlib only)."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import TypedDict

logger = logging.getLogger(__name__)

APOD_URL = "https://api.nasa.gov/planetary/apod"
DEFAULT_API_KEY = "DEMO_KEY"
TIMEOUT = 15


class ApodError(RuntimeError):
    """Raised when the APOD endpoint is unreachable or returns unusable data."""


class Apod(TypedDict):
    date: str
    title: str
    explanation: str
    url: str
    hdurl: str | None
    media_type: str
    copyright: str | None


def fetch_apod(api_key: str | None = None) -> Apod | None:
    """Return today's APOD, or None if media_type=='video'.

    Raises ApodError on network/HTTP failure.
    """
    key = api_key or os.environ.get("NASA_API_KEY") or DEFAULT_API_KEY
    url = f"{APOD_URL}?api_key={key}"

    logger.info("Fetching NASA APOD (key=%s)", "DEMO_KEY" if key == DEFAULT_API_KEY else "user")
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        raise ApodError(f"APOD fetch failed: {e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ApodError(f"APOD returned non-JSON: {e}") from e

    if data.get("media_type") == "video":
        logger.info("APOD is a video today, skipping")
        return None

    required = ("date", "title", "explanation", "url", "media_type")
    if not all(k in data for k in required):
        raise ApodError(f"APOD payload missing fields: {data}")

    return Apod(
        date=data["date"],
        title=data["title"],
        explanation=data["explanation"],
        url=data["url"],
        hdurl=data.get("hdurl"),
        media_type=data["media_type"],
        copyright=data.get("copyright"),
    )


def render_apod_markdown(apod: Apod) -> str:
    """Top-of-digest block. Non-LLM, just formatting."""
    lines = [
        "## 🌌 NASA Astronomy Picture of the Day",
        "",
        f"**{apod['title']}** — _{apod['date']}_",
        "",
        f"![{apod['title']}]({apod['url']})",
        "",
        apod["explanation"].strip(),
        "",
    ]
    if apod.get("copyright"):
        lines.append(f"_Image credit: {apod['copyright'].strip()}_")
        lines.append("")
    if apod.get("hdurl"):
        lines.append(f"[HD image]({apod['hdurl']})")
        lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)
