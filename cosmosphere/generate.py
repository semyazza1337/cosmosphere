"""Render a ScoredPaper list into a markdown digest with YAML frontmatter."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import frontmatter

from .models import ScoredPaper

logger = logging.getLogger(__name__)


def _render_body(papers: list[ScoredPaper], apod_block: str | None = None) -> str:
    parts: list[str] = []
    if apod_block:
        parts.append(apod_block)

    if not papers:
        parts.append("_No papers cleared the relevance threshold today._\n")
        return "".join(parts)

    lines: list[str] = []
    for p in papers:
        lines.append(f"## {p.title}")
        lines.append("")
        lines.append(f"**Score:** {p.relevance_score}/10  ")
        lines.append(f"**arXiv:** [{p.arxiv_id}]({p.link})  ")
        if p.authors:
            authors = ", ".join(p.authors[:5]) + (" et al." if len(p.authors) > 5 else "")
            lines.append(f"**Authors:** {authors}  ")
        if p.categories:
            lines.append(f"**Categories:** {', '.join(p.categories)}  ")
        lines.append("")
        lines.append(f"{p.why_interesting}")
        lines.append("")
        lines.append("---")
        lines.append("")
    parts.append("\n".join(lines))
    return "".join(parts)


def _papers_frontmatter(papers: list[ScoredPaper]) -> list[dict]:
    return [
        {
            "arxiv_id": p.arxiv_id,
            "title": p.title,
            "score": p.relevance_score,
            "link": str(p.link),
            "why_interesting": p.why_interesting,
        }
        for p in papers
    ]


def write_digest(
    papers: list[ScoredPaper],
    out_dir: Path,
    *,
    today: date | None = None,
    apod_block: str | None = None,
    extra_meta: dict | None = None,
) -> Path:
    """Write data/digests/YYYY-MM-DD.md and return its path."""
    today = today or date.today()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{today.isoformat()}.md"

    papers_sorted = sorted(papers, key=lambda p: (-p.relevance_score, p.title))

    meta: dict = {
        "date": today.isoformat(),
        "paper_count": len(papers_sorted),
        "papers": _papers_frontmatter(papers_sorted),
        "generated_by": "cosmosphere",
    }
    if extra_meta:
        meta.update(extra_meta)

    post = frontmatter.Post(
        content=_render_body(papers_sorted, apod_block=apod_block),
        **meta,
    )

    out_path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    logger.info("Wrote digest to %s", out_path)
    return out_path
