"""Tests for ADK agent tools (unit tests — no LLM calls)."""

from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta

from file_fetcher.agent.tools import (
    make_search_tool,
    make_ratings_tool,
    sanitize_query,
    _MAX_QUERY_LENGTH,
    _MAX_AGE_DAYS_CAP,
)
from file_fetcher.scanner import MediaEntry
from file_fetcher.ratings import Ratings


# ── sanitize_query (preserved from old llm/base.py) ──────────────────────


def test_sanitize_query_strips_control_chars():
    raw = "find movies\x00\x01\x0b\x7f about space"
    assert sanitize_query(raw) == "find movies about space"


def test_sanitize_query_preserves_normal_whitespace():
    raw = "find recent\tmovies\nfrom 2026"
    assert sanitize_query(raw) == raw


def test_sanitize_query_truncates_long_input():
    raw = "a" * 1000
    result = sanitize_query(raw)
    assert len(result) == _MAX_QUERY_LENGTH


# ── make_search_tool ──────────────────────────────────────────────────────


def test_search_tool_calls_scanner_and_returns_dict():
    mock_scanner = Mock()
    now = datetime.now()
    mock_scanner.scan.return_value = [
        MediaEntry(
            title="Test Movie",
            year=2026,
            remote_path="Media1/Films/Test Movie (2026)",
            modified_date=now,
            size_bytes=5_000_000,
            media_type="movie",
        )
    ]

    search = make_search_tool(mock_scanner)
    result = search(media_type="movies", year=2026)

    mock_scanner.scan.assert_called_once_with(
        media_type="movies", year=2026, max_age_days=None, keywords=None
    )
    assert result["status"] == "success"
    assert result["count"] == 1
    assert result["results"][0]["title"] == "Test Movie"
    assert result["results"][0]["index"] == 0


def test_search_tool_caps_max_age_days():
    mock_scanner = Mock()
    mock_scanner.scan.return_value = []

    search = make_search_tool(mock_scanner)
    search(max_age_days=99999)

    # Should have been capped to _MAX_AGE_DAYS_CAP
    mock_scanner.scan.assert_called_once_with(
        media_type="all", year=None, max_age_days=_MAX_AGE_DAYS_CAP, keywords=None
    )


def test_search_tool_passes_keywords():
    mock_scanner = Mock()
    mock_scanner.scan.return_value = []

    search = make_search_tool(mock_scanner)
    search(media_type="all", keywords=["1080p"])

    mock_scanner.scan.assert_called_once_with(
        media_type="all", year=None, max_age_days=None, keywords=["1080p"]
    )


# ── make_ratings_tool ─────────────────────────────────────────────────────


@patch("file_fetcher.agent.tools._get_ratings")
def test_ratings_tool_calls_get_ratings(mock_get_ratings):
    mock_get_ratings.return_value = Ratings(
        imdb="8.5",
        rotten_tomatoes="92%",
        genre="Sci-Fi",
        plot="A test plot.",
        director="Director X",
        actors="Actor A, Actor B",
    )

    ratings = make_ratings_tool("test_api_key")
    result = ratings(title="Test Movie", year=2026)

    mock_get_ratings.assert_called_once_with("Test Movie", 2026, "test_api_key")
    assert result["status"] == "success"
    assert result["imdb"] == "8.5"
    assert result["rotten_tomatoes"] == "92%"
    assert result["genre"] == "Sci-Fi"


@patch("file_fetcher.agent.tools._get_ratings")
def test_ratings_tool_without_year(mock_get_ratings):
    mock_get_ratings.return_value = Ratings(imdb="N/A", rotten_tomatoes="N/A")

    ratings = make_ratings_tool("key123")
    result = ratings(title="Unknown")

    mock_get_ratings.assert_called_once_with("Unknown", None, "key123")
    assert result["status"] == "success"
    assert result["imdb"] == "N/A"
