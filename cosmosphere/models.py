"""Shared Pydantic models for the cosmosphere pipeline."""

from __future__ import annotations

from datetime import date
from pydantic import BaseModel, Field, HttpUrl


class Paper(BaseModel):
    """A single arxiv paper extracted from the RSS feed."""

    arxiv_id: str = Field(..., description="e.g. '2504.12345'")
    title: str
    authors: list[str] = Field(default_factory=list)
    summary: str
    categories: list[str] = Field(default_factory=list)
    published: date
    link: HttpUrl

    def prompt_block(self) -> str:
        """Compact representation for Claude prompt."""
        auth = ", ".join(self.authors[:5]) + (" et al." if len(self.authors) > 5 else "")
        cats = ", ".join(self.categories)
        return (
            f"arxiv_id: {self.arxiv_id}\n"
            f"title: {self.title}\n"
            f"authors: {auth}\n"
            f"categories: {cats}\n"
            f"abstract: {self.summary.strip()}"
        )


class ScoredPaper(Paper):
    """A Paper enriched with Claude-assigned taste score."""

    relevance_score: int = Field(..., ge=1, le=10)
    why_interesting: str
