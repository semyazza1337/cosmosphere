"""`cosmosphere weekly` — weekly roundup from last 7 days of digests."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

import frontmatter

from .providers import ProviderError, call_provider
from .publish import PublishError, publish_to_blog

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
WEEKLY_PROMPT = PROMPTS_DIR / "weekly_writer.md"

LANG_CLAUSE = {
    "pl": "Write the roundup in Polish.",
    "en": "Write the roundup in English.",
}

TOP_N = 7
MIN_N = 5


class WeeklyError(RuntimeError):
    """Raised when no digests are found or LLM call fails."""


def _load_prompt() -> str:
    if not WEEKLY_PROMPT.exists():
        raise WeeklyError(f"Missing weekly prompt at {WEEKLY_PROMPT}")
    return WEEKLY_PROMPT.read_text(encoding="utf-8")


def _collect_last_week(digest_dir: Path, today: date) -> list[dict]:
    """Walk last 7 days of digests, aggregate their `papers` frontmatter arrays."""
    cutoff = today - timedelta(days=7)
    collected: dict[str, dict] = {}

    for p in sorted(digest_dir.glob("*.md")):
        try:
            d = date.fromisoformat(p.stem)
        except ValueError:
            continue
        if d < cutoff or d > today:
            continue

        post = frontmatter.load(str(p))
        for entry in post.metadata.get("papers") or []:
            aid = entry.get("arxiv_id")
            if not aid:
                continue
            existing = collected.get(aid)
            if not existing or int(entry.get("score", 0)) > int(existing.get("score", 0)):
                collected[aid] = entry

    return list(collected.values())


def _iso_week_label(today: date) -> str:
    y, w, _ = today.isocalendar()
    return f"{y}-W{w:02d}"


def _build_user_msg(picked: list[dict], week_label: str) -> str:
    blocks = []
    for p in picked:
        blocks.append(
            f"arxiv_id: {p['arxiv_id']}\n"
            f"title: {p['title']}\n"
            f"score: {p['score']}/10\n"
            f"link: {p['link']}\n"
            f"why_interesting: {p['why_interesting']}"
        )
    joined = "\n\n---\n\n".join(blocks)
    return (
        f"Week: {week_label}\n"
        f"{len(picked)} top papers from the past 7 days of arxiv astro-ph.HE:\n\n"
        f"{joined}\n\n"
        "Write a weekly roundup per the system prompt. "
        "Return markdown only (no YAML frontmatter). Start with an H1."
    )


def generate_weekly(
    *,
    provider: str = "anthropic",
    mode: str = "expert",
    lang: str = "en",
    publish: bool = False,
    today: date | None = None,
    digest_dir: Path | None = None,
    out_dir: Path | None = None,
) -> Path:
    today = today or date.today()
    digest_dir = digest_dir or Path(__file__).resolve().parent.parent / "data" / "digests"
    out_dir = out_dir or Path(__file__).resolve().parent.parent / "data" / "weekly"

    all_papers = _collect_last_week(digest_dir, today)
    if not all_papers:
        raise WeeklyError(f"No digests with `papers` frontmatter in last 7 days under {digest_dir}")

    all_papers.sort(key=lambda p: -int(p.get("score", 0)))
    picked = all_papers[:TOP_N]
    if len(picked) < MIN_N and len(all_papers) >= MIN_N:
        picked = all_papers[:MIN_N]
    logger.info("Weekly: %d unique papers, picked top %d", len(all_papers), len(picked))

    week_label = _iso_week_label(today)
    system_prompt = _load_prompt()
    clause = LANG_CLAUSE.get(lang)
    if clause:
        system_prompt = f"{system_prompt}\n\n## Language\n\n{clause}"
    system_prompt = f"{system_prompt}\n\n## Mode\n\nMode: {mode}"

    user_msg = _build_user_msg(picked, week_label)

    try:
        body = call_provider(provider, system_prompt, user_msg).strip()
    except ProviderError as e:
        raise WeeklyError(str(e)) from e

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{week_label}.md"

    fm_post = frontmatter.Post(
        content=body,
        **{
            "title": f"Astro weekly — {week_label}",
            "date": today.isoformat(),
            "week": week_label,
            "tags": ["astronomy", "cosmosphere", "weekly"],
            "mode": mode,
            "lang": lang,
            "paper_count": len(picked),
            "arxiv_ids": [p["arxiv_id"] for p in picked],
            "generated_by": "cosmosphere",
        },
    )
    out_path.write_text(frontmatter.dumps(fm_post) + "\n", encoding="utf-8")
    logger.info("Wrote weekly to %s", out_path)

    if publish:
        try:
            publish_to_blog(
                out_path,
                subdir="weekly",
                commit_msg=f"weekly: {week_label}",
            )
        except PublishError as e:
            raise WeeklyError(f"Weekly written but publish failed: {e}") from e

    return out_path
