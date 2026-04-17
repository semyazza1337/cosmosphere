"""`cosmosphere explain <arxiv_id>` — deep-dive a single paper."""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import frontmatter

from .models import Paper
from .providers import ProviderError, call_provider

logger = logging.getLogger(__name__)

ARXIV_API = "http://export.arxiv.org/api/query?id_list={id}"
ATOM_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}
TIMEOUT = 20
_ID_RE = re.compile(r"(\d{4}\.\d{4,6})")

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
PROMPT_BY_MODE = {
    "expert": PROMPTS_DIR / "explain_expert.md",
    "amateur": PROMPTS_DIR / "explain_amateur.md",
}
LANG_CLAUSE = {
    "pl": "Respond in Polish.",
    "en": "Respond in English.",
}


class ExplainError(RuntimeError):
    """Raised when the arxiv API fails or the LLM cannot explain."""


def fetch_paper_by_id(arxiv_id: str) -> Paper:
    """Fetch a single paper via the arxiv Atom API. Raises ExplainError."""
    m = _ID_RE.search(arxiv_id)
    if not m:
        raise ExplainError(f"Invalid arxiv id format: {arxiv_id!r}")
    clean_id = m.group(1)

    url = ARXIV_API.format(id=clean_id)
    logger.info("Fetching %s", url)
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
            xml_bytes = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        raise ExplainError(f"arxiv API fetch failed: {e}") from e

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ExplainError(f"arxiv API returned non-XML: {e}") from e

    entry = root.find("atom:entry", ATOM_NS)
    if entry is None:
        raise ExplainError(f"arxiv API returned no entry for {clean_id}")

    title_el = entry.find("atom:title", ATOM_NS)
    summary_el = entry.find("atom:summary", ATOM_NS)
    published_el = entry.find("atom:published", ATOM_NS)
    link_el = entry.find("atom:id", ATOM_NS)

    if title_el is None or summary_el is None:
        raise ExplainError(f"arxiv entry missing title/summary for {clean_id}")

    authors = [
        a.findtext("atom:name", default="", namespaces=ATOM_NS).strip()
        for a in entry.findall("atom:author", ATOM_NS)
    ]
    authors = [a for a in authors if a]

    categories = [
        c.attrib.get("term", "")
        for c in entry.findall("atom:category", ATOM_NS)
    ]
    categories = [c for c in categories if c]

    pub_date = date.today()
    if published_el is not None and published_el.text:
        try:
            pub_date = datetime.fromisoformat(
                published_el.text.replace("Z", "+00:00")
            ).astimezone(timezone.utc).date()
        except ValueError:
            pass

    link = (link_el.text if link_el is not None and link_el.text else
            f"https://arxiv.org/abs/{clean_id}").strip()

    return Paper(
        arxiv_id=clean_id,
        title=re.sub(r"\s+", " ", title_el.text.strip()),
        authors=authors,
        summary=re.sub(r"\s+", " ", summary_el.text.strip()),
        categories=categories,
        published=pub_date,
        link=link,
    )


def _load_prompt(mode: str) -> str:
    path = PROMPT_BY_MODE.get(mode)
    if path is None:
        raise ExplainError(f"Unknown mode {mode!r}. Choose: {list(PROMPT_BY_MODE)}")
    if not path.exists():
        raise ExplainError(f"Missing explain prompt at {path}")
    return path.read_text(encoding="utf-8")


def explain_paper(
    arxiv_id: str,
    *,
    provider: str = "anthropic",
    mode: str = "expert",
    lang: str = "en",
    out_dir: Path | None = None,
) -> tuple[Path, str]:
    """Fetch + explain a paper. Returns (output_path, explanation_text)."""
    paper = fetch_paper_by_id(arxiv_id)

    system_prompt = _load_prompt(mode)
    clause = LANG_CLAUSE.get(lang)
    if clause:
        system_prompt = f"{system_prompt}\n\n## Language\n\n{clause}"

    user_msg = (
        "Explain this paper in 600-800 words following the system prompt style.\n\n"
        f"{paper.prompt_block()}\n\n"
        f"Link: {paper.link}"
    )

    try:
        text = call_provider(provider, system_prompt, user_msg).strip()
    except ProviderError as e:
        raise ExplainError(str(e)) from e

    if out_dir is None:
        out_dir = Path(__file__).resolve().parent.parent / "data" / "explanations"
    out_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    out_path = out_dir / f"{today}-{paper.arxiv_id}.md"

    post = frontmatter.Post(
        content=text,
        **{
            "title": paper.title,
            "arxiv_id": paper.arxiv_id,
            "link": str(paper.link),
            "authors": paper.authors,
            "categories": paper.categories,
            "published": paper.published.isoformat(),
            "mode": mode,
            "lang": lang,
            "provider": provider,
            "generated_by": "cosmosphere",
            "date": today,
        },
    )
    out_path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    logger.info("Wrote explanation to %s", out_path)
    return out_path, text
