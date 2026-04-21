"""Tests for analyze._extract_json_array — regression for nested bracket bug."""

from __future__ import annotations

import pytest

from cosmosphere.analyze import AnalyzeError, _extract_json_array


def test_plain_array():
    text = '[{"arxiv_id": "2504.1", "relevance_score": 8, "why_interesting": "x"}]'
    result = _extract_json_array(text)
    assert len(result) == 1
    assert result[0]["arxiv_id"] == "2504.1"


def test_array_with_markdown_fence():
    text = (
        "Here you go:\n"
        '```json\n'
        '[{"arxiv_id": "2504.1", "relevance_score": 8, "why_interesting": "x"}]\n'
        '```\n'
    )
    result = _extract_json_array(text)
    assert result[0]["arxiv_id"] == "2504.1"


def test_array_with_nested_array_in_field():
    """LLM sometimes echoes authors list — must not truncate on first `]`."""
    text = (
        '[{"arxiv_id": "2504.1", "relevance_score": 8, '
        '"why_interesting": "authors include [Smith, Jones]", '
        '"extra": [1, 2, 3]}]'
    )
    result = _extract_json_array(text)
    assert len(result) == 1
    assert result[0]["extra"] == [1, 2, 3]


def test_array_with_prose_prefix():
    text = 'Sure, here are the scores: [{"arxiv_id": "2504.1", "relevance_score": 5, "why_interesting": "ok"}]'
    result = _extract_json_array(text)
    assert len(result) == 1


def test_no_array_raises():
    with pytest.raises(AnalyzeError):
        _extract_json_array("Sorry, I cannot comply.")


def test_invalid_json_raises():
    with pytest.raises(AnalyzeError):
        _extract_json_array("[{malformed]")
