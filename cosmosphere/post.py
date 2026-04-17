"""`cosmosphere post` — generate a ~500-word blog post from a digest."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import frontmatter

from .providers import ProviderError, call_provider
from .publish import PublishError, publish_to_blog

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
POST_PROMPT = PROMPTS_DIR / "post_writer.md"

LANG_CLAUSE = {
    "pl": "Write the post in Polish.",
    "en": "Write the post in English.",
}

TOP_SCORE_FLOOR = 8


class PostError(RuntimeError):
    """Raised when the digest cannot be read or the LLM post generation fails."""


def _load_prompt() -> str:
    if not POST_PROMPT.exists():
        raise PostError(f"Missing post prompt at {POST_PROMPT}")
    return POST_PROMPT.read_text(encoding="utf-8")


def _select_papers(meta: dict) -> list[dict]:
    papers = meta.get("papers") or []
    if not papers:
        raise PostError(
            "Digest frontmatter has no `papers` array — regenerate digest first."
        )
    top = [p for p in papers if int(p.get("score", 0)) >= TOP_SCORE_FLOOR]
    if top:
        return top
    papers_sorted = sorted(papers, key=lambda p: -int(p.get("score", 0)))
    return papers_sorted[:1]


def _build_user_msg(picked: list[dict], digest_date: str) -> str:
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
        f"Digest date: {digest_date}\n"
        f"Papers selected (top {len(picked)}):\n\n{joined}\n\n"
        "Write a ~500-word blog post in the style defined by the system prompt. "
        "Do NOT include YAML frontmatter — only the post body in markdown. "
        "Start with an H1 title."
    )


def generate_post(
    *,
    target_date: date | None = None,
    provider: str = "anthropic",
    mode: str = "expert",
    lang: str = "en",
    publish: bool = False,
    digest_dir: Path | None = None,
    out_dir: Path | None = None,
) -> Path:
    target_date = target_date or date.today()
    digest_dir = digest_dir or Path(__file__).resolve().parent.parent / "data" / "digests"
    out_dir = out_dir or Path(__file__).resolve().parent.parent / "data" / "posts"

    digest_path = digest_dir / f"{target_date.isoformat()}.md"
    if not digest_path.exists():
        raise PostError(f"No digest for {target_date}: {digest_path}")

    digest_post = frontmatter.load(str(digest_path))
    picked = _select_papers(digest_post.metadata)
    logger.info("Selected %d paper(s) for blog post", len(picked))

    system_prompt = _load_prompt()
    clause = LANG_CLAUSE.get(lang)
    if clause:
        system_prompt = f"{system_prompt}\n\n## Language\n\n{clause}"
    system_prompt = f"{system_prompt}\n\n## Mode\n\nMode: {mode}"

    user_msg = _build_user_msg(picked, target_date.isoformat())

    try:
        body = call_provider(provider, system_prompt, user_msg).strip()
    except ProviderError as e:
        raise PostError(str(e)) from e

    title = f"Cosmosphere digest — {target_date.isoformat()}"
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            title = s[2:].strip()
            break

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{target_date.isoformat()}.md"

    fm_post = frontmatter.Post(
        content=body,
        **{
            "title": title,
            "date": target_date.isoformat(),
            "tags": ["astronomy", "cosmosphere"],
            "mode": mode,
            "lang": lang,
            "source_digest": digest_path.name,
            "arxiv_ids": [p["arxiv_id"] for p in picked],
            "generated_by": "cosmosphere",
        },
    )
    out_path.write_text(frontmatter.dumps(fm_post) + "\n", encoding="utf-8")
    logger.info("Wrote post to %s", out_path)

    if publish:
        try:
            publish_to_blog(
                out_path,
                subdir="digest",
                commit_msg=f"post: {target_date.isoformat()}",
            )
        except PublishError as e:
            raise PostError(f"Post written but publish failed: {e}") from e

    return out_path
