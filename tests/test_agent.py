"""Tests for ADK agent tools (unit tests — no LLM calls)."""

from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
import inspect
import json

from file_fetcher.agent.tools import (
    make_search_tool,
    make_ratings_tool,
    make_catalog_search_tool,
    sanitize_query,
    _MAX_QUERY_LENGTH,
    _MAX_AGE_DAYS_CAP,
)
from file_fetcher.schemas.catalog import CatalogResult
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


# ── make_catalog_search_tool (Story 5.2) ─────────────────────────────────


@patch("file_fetcher.services.catalog.search_catalog")
@patch("file_fetcher.db.get_session")
def test_catalog_search_tool_calls_search_catalog(mock_get_session, mock_search_catalog):
    """Tool calls catalog_service.search_catalog and returns list of dicts."""
    mock_result = CatalogResult(
        id=1,
        title="The Matrix",
        year=1999,
        media_type="film",
        omdb_status="enriched",
        availability="remote_only",
        remote_paths=["/media/matrix.mkv"],
        local_paths=[],
        imdb_rating="8.7",
        genre="Action, Sci-Fi",
    )
    mock_search_catalog.return_value = [mock_result]

    # Patch get_session as context manager
    mock_session = MagicMock()
    mock_session_ctx = MagicMock()
    mock_session_ctx.__enter__ = Mock(return_value=mock_session)
    mock_session_ctx.__exit__ = Mock(return_value=False)
    mock_get_session.return_value = mock_session_ctx

    tool = make_catalog_search_tool()
    results = tool(query="Matrix")

    assert len(results) == 1
    assert results[0]["title"] == "The Matrix"
    assert results[0]["year"] == 1999
    assert results[0]["availability"] == "remote_only"
    assert results[0]["imdb_rating"] == "8.7"
    assert results[0]["genre"] == "Action, Sci-Fi"


@patch("file_fetcher.services.catalog.search_catalog")
@patch("file_fetcher.db.get_session")
def test_catalog_search_tool_with_media_type(mock_get_session, mock_search_catalog):
    """Tool passes media_type through to search_catalog."""
    mock_search_catalog.return_value = []
    mock_session = MagicMock()
    mock_session_ctx = MagicMock()
    mock_session_ctx.__enter__ = Mock(return_value=mock_session)
    mock_session_ctx.__exit__ = Mock(return_value=False)
    mock_get_session.return_value = mock_session_ctx

    tool = make_catalog_search_tool()
    tool(query="sci-fi", media_type="film")

    mock_search_catalog.assert_called_once_with(mock_session, "sci-fi", media_type="film", limit=50)


@patch("file_fetcher.services.catalog.search_catalog")
@patch("file_fetcher.db.get_session")
def test_catalog_search_tool_empty_results(mock_get_session, mock_search_catalog):
    """Tool returns empty list when no results found."""
    mock_search_catalog.return_value = []
    mock_session_ctx = MagicMock()
    mock_session_ctx.__enter__ = Mock(return_value=MagicMock())
    mock_session_ctx.__exit__ = Mock(return_value=False)
    mock_get_session.return_value = mock_session_ctx

    tool = make_catalog_search_tool()
    results = tool(query="zzz_no_match")

    assert results == []


@patch("file_fetcher.db.get_session")
def test_catalog_search_tool_db_error_returns_empty(mock_get_session):
    """Tool returns empty list gracefully when DB raises an exception."""
    mock_get_session.side_effect = Exception("DB connection failed")

    tool = make_catalog_search_tool()
    results = tool(query="anything")

    assert results == []


def test_catalog_search_tool_schema():
    """search_catalog_db function has correct signature for ADK tool."""
    tool = make_catalog_search_tool()
    sig = inspect.signature(tool)
    params = list(sig.parameters.keys())

    assert "query" in params
    assert "media_type" in params
    # query has no default; media_type defaults to None
    assert sig.parameters["media_type"].default is None


# ── run_catalog_agent (Story 5.2) — graceful AI fallback ─────────────────

@patch("file_fetcher.agent.agent.asyncio.run")
def test_run_catalog_agent_parses_json_array(mock_asyncio_run):
    """run_catalog_agent parses JSON array from agent response."""
    from file_fetcher.agent.agent import run_catalog_agent

    payload = json.dumps([
        {"title": "Inception", "year": 2010, "media_type": "film",
         "availability": "remote_only", "imdb_rating": "8.8", "genre": "Sci-Fi"},
    ])
    mock_asyncio_run.return_value = payload

    results = run_catalog_agent(Mock(), "sci-fi")

    assert len(results) == 1
    assert results[0]["title"] == "Inception"


@patch("file_fetcher.agent.agent.asyncio.run")
def test_run_catalog_agent_handles_api_error_response(mock_asyncio_run):
    """run_catalog_agent returns empty list on graceful error response."""
    from file_fetcher.agent.agent import run_catalog_agent

    mock_asyncio_run.return_value = '{"error": "AI search unavailable. Please try a direct search."}'

    results = run_catalog_agent(Mock(), "sci-fi")
    assert results == []


@patch("file_fetcher.agent.agent.asyncio.run")
def test_run_catalog_agent_empty_response_returns_empty(mock_asyncio_run):
    """run_catalog_agent returns empty list when agent returns empty string."""
    from file_fetcher.agent.agent import run_catalog_agent

    mock_asyncio_run.return_value = ""

    results = run_catalog_agent(Mock(), "anything")
    assert results == []


@patch("file_fetcher.agent.agent.asyncio.run")
def test_run_catalog_agent_strips_markdown_fences(mock_asyncio_run):
    """run_catalog_agent strips ```json ... ``` fences before parsing."""
    from file_fetcher.agent.agent import run_catalog_agent

    payload = '```json\n[{"title": "Dune", "year": 2021}]\n```'
    mock_asyncio_run.return_value = payload

    results = run_catalog_agent(Mock(), "dune")
    assert len(results) == 1
    assert results[0]["title"] == "Dune"
