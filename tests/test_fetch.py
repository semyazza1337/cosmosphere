"""Tests for fetch.py — fixture RSS blob, no network."""

from __future__ import annotations

from unittest.mock import patch

import feedparser
import pytest

from cosmosphere.fetch import FetchError, _extract_arxiv_id, fetch_papers

FAKE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>astro-ph.HE updates</title>
    <link>https://arxiv.org/list/astro-ph.HE/recent</link>
    <description>test</description>
    <item>
      <title>Evidence for a Kerr black hole in NGC 1234</title>
      <link>https://arxiv.org/abs/2504.11111</link>
      <guid>oai:arXiv.org:2504.11111v1</guid>
      <description>&lt;p&gt;Abstract: We report a spin measurement of 0.9.&lt;/p&gt;</description>
      <pubDate>Thu, 17 Apr 2026 00:00:00 GMT</pubDate>
      <author>Alice Smith, Bob Jones</author>
      <category>astro-ph.HE</category>
    </item>
    <item>
      <title>Routine X-ray catalogue extension</title>
      <link>https://arxiv.org/abs/2504.22222</link>
      <guid>oai:arXiv.org:2504.22222v1</guid>
      <description>Abstract: 47 new sources.</description>
      <pubDate>Thu, 17 Apr 2026 00:00:00 GMT</pubDate>
      <author>Carol Davis</author>
      <category>astro-ph.HE</category>
    </item>
  </channel>
</rss>
"""


@pytest.fixture
def parsed_feed():
    return feedparser.parse(FAKE_RSS)


def test_extract_arxiv_id_from_guid():
    class E(dict):
        pass

    e = E(id="oai:arXiv.org:2504.12345v1", guid="", link="")
    assert _extract_arxiv_id(e) == "2504.12345"


def test_extract_arxiv_id_from_link():
    class E(dict):
        pass

    e = E(id="", guid="", link="https://arxiv.org/abs/2501.99999")
    assert _extract_arxiv_id(e) == "2501.99999"


def test_extract_arxiv_id_none_when_absent():
    class E(dict):
        pass

    e = E(id="", guid="", link="https://example.com/no-id-here")
    assert _extract_arxiv_id(e) is None


def test_fetch_papers_returns_papers_not_in_seen(parsed_feed):
    with patch("cosmosphere.fetch.feedparser.parse", return_value=parsed_feed):
        papers = fetch_papers(seen=set())
    assert len(papers) == 2
    ids = {p.arxiv_id for p in papers}
    assert ids == {"2504.11111", "2504.22222"}


def test_fetch_papers_filters_seen(parsed_feed):
    with patch("cosmosphere.fetch.feedparser.parse", return_value=parsed_feed):
        papers = fetch_papers(seen={"2504.11111"})
    assert len(papers) == 1
    assert papers[0].arxiv_id == "2504.22222"


def test_fetch_papers_strips_html_and_abstract_prefix(parsed_feed):
    with patch("cosmosphere.fetch.feedparser.parse", return_value=parsed_feed):
        papers = fetch_papers(seen=set())
    p = next(p for p in papers if p.arxiv_id == "2504.11111")
    assert "<p>" not in p.summary
    assert not p.summary.lower().startswith("abstract:")
    assert "spin measurement" in p.summary


def test_fetch_papers_raises_on_empty_feed():
    empty = feedparser.parse("<?xml version='1.0'?><rss><channel></channel></rss>")
    with patch("cosmosphere.fetch.feedparser.parse", return_value=empty):
        with pytest.raises(FetchError):
            fetch_papers(seen=set())


def test_paper_prompt_block_truncates_authors(parsed_feed):
    with patch("cosmosphere.fetch.feedparser.parse", return_value=parsed_feed):
        papers = fetch_papers(seen=set())
    block = papers[0].prompt_block()
    assert "arxiv_id: 2504.11111" in block
    assert "title:" in block
    assert "abstract:" in block
