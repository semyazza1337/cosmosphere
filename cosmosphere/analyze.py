"""Send a batch of Papers to the configured LLM provider, receive taste-based scores."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .models import Paper, ScoredPaper
from .providers import ProviderError, call_provider

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
PROMPT_BY_MODE = {
    "expert": PROMPTS_DIR / "astro_taste_expert.md",
    "amateur": PROMPTS_DIR / "astro_taste_amateur.md",
}
LANG_CLAUSE = {
    "pl": "Write every `why_interesting` field in Polish.",
    "en": "Write every `why_interesting` field in English.",
}
DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODE = "expert"
DEFAULT_LANG = "en"

logger = logging.getLogger(__name__)


class AnalyzeError(RuntimeError):
    """Raised when the LLM call fails or returns unparseable output."""


def _load_system_prompt(mode: str, lang: str) -> str:
    path = PROMPT_BY_MODE.get(mode)
    if path is None:
        raise AnalyzeError(f"Unknown mode {mode!r}. Choose: {list(PROMPT_BY_MODE)}")
    if not path.exists():
        raise AnalyzeError(f"Missing taste prompt at {path}")
    base = path.read_text(encoding="utf-8")
    clause = LANG_CLAUSE.get(lang)
    if clause is None:
        raise AnalyzeError(f"Unknown lang {lang!r}. Choose: {list(LANG_CLAUSE)}")
    return f"{base}\n\n## Language override\n\n{clause}"


def _build_user_message(papers: list[Paper]) -> str:
    blocks = "\n\n---\n\n".join(p.prompt_block() for p in papers)
    return (
        f"Here are {len(papers)} new astro-ph.HE papers from today. "
        "Score each one 1–10 against the taste profile in the system prompt.\n\n"
        "Respond with ONLY a JSON array, no prose, no markdown fence. "
        "Each element must be:\n"
        '{"arxiv_id": "<id>", "relevance_score": <int 1-10>, '
        '"why_interesting": "<1-2 sentences, plain English, no hype>"}\n\n'
        f"Papers:\n\n{blocks}"
    )


def _extract_json_array(text: str) -> list[dict]:
    """Parse a JSON array from the LLM reply, tolerating markdown fences."""
    fence = re.search(r"```(?:json)?\s*(\[.*\])\s*```", text, re.DOTALL)
    payload = fence.group(1) if fence else text

    if not payload.strip().startswith("["):
        start = payload.find("[")
        end = payload.rfind("]")
        if start == -1 or end == -1 or end <= start:
            raise AnalyzeError("No JSON array found in LLM response")
        payload = payload[start : end + 1]

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        raise AnalyzeError(f"Invalid JSON from LLM: {e}") from e

    if not isinstance(data, list):
        raise AnalyzeError("Expected JSON array at top level")
    return data


def score_papers(
    papers: list[Paper],
    *,
    provider: str = DEFAULT_PROVIDER,
    mode: str = DEFAULT_MODE,
    lang: str = DEFAULT_LANG,
) -> list[ScoredPaper]:
    """Single batched LLM call. Returns ScoredPaper list."""
    if not papers:
        return []

    system_prompt = _load_system_prompt(mode, lang)
    user_msg = _build_user_message(papers)

    try:
        text = call_provider(provider, system_prompt, user_msg)
    except ProviderError as e:
        raise AnalyzeError(str(e)) from e

    raw_scores = _extract_json_array(text)

    by_id = {p.arxiv_id: p for p in papers}
    scored: list[ScoredPaper] = []
    for item in raw_scores:
        aid = item.get("arxiv_id")
        paper = by_id.get(aid)
        if not paper:
            logger.warning("LLM returned unknown arxiv_id %r, skipping", aid)
            continue
        try:
            scored.append(
                ScoredPaper(
                    **paper.model_dump(),
                    relevance_score=int(item["relevance_score"]),
                    why_interesting=str(item["why_interesting"]).strip(),
                )
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.warning("Malformed score entry for %s: %s", aid, e)
            continue

    logger.info("Scored %d/%d papers", len(scored), len(papers))
    return scored
