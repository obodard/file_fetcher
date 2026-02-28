"""Unit tests for the `file-fetcher search` CLI command (Story 5.3)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from file_fetcher.cli.search import search
from file_fetcher.models.base import Base
from file_fetcher.models.enums import MediaType, OmdbStatus
from file_fetcher.models.movie import Movie
from file_fetcher.models.omdb_data import OmdbData
from file_fetcher.models.remote_file import RemoteFile
from file_fetcher.models.show import Show


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def patch_get_session(db_session, monkeypatch):
    """Replace get_session with the in-memory test session."""

    @contextmanager
    def _fake_get_session():
        yield db_session

    monkeypatch.setattr("file_fetcher.cli.search.get_session", _fake_get_session)


@pytest.fixture()
def runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _movie(
    session: Session,
    title: str = "Inception",
    year: int = 2010,
    genre: str | None = "Sci-Fi",
    imdb_rating: str | None = "8.8",
) -> Movie:
    m = Movie(
        title=title,
        year=year,
        media_type=MediaType.film,
        omdb_status=OmdbStatus.ENRICHED,
    )
    session.add(m)
    session.flush()
    if genre or imdb_rating:
        session.add(
            OmdbData(
                movie_id=m.id,
                genre=genre,
                imdb_rating=imdb_rating,
            )
        )
        session.flush()
    rf = RemoteFile(
        movie_id=m.id,
        remote_path=f"/media/{title.replace(' ', '_')}.mkv",
        filename=f"{title}.mkv",
        media_type=MediaType.film,
    )
    session.add(rf)
    session.flush()
    return m


def _show(session: Session, title: str = "Chernobyl", year: int = 2019) -> Show:
    s = Show(
        title=title,
        year=year,
        media_type=MediaType.series,
        omdb_status=OmdbStatus.ENRICHED,
    )
    session.add(s)
    session.flush()
    session.add(
        OmdbData(
            show_id=s.id,
            genre="Drama",
            imdb_rating="9.4",
        )
    )
    session.flush()
    return s


# ---------------------------------------------------------------------------
# Basic invocation (--no-ai)
# ---------------------------------------------------------------------------


def test_search_no_ai_returns_tabular_output(runner, db_session):
    _movie(db_session, title="The Matrix", year=1999)

    result = runner.invoke(search, ["Matrix", "--no-ai"])

    assert result.exit_code == 0
    assert "The Matrix" in result.output
    assert "1999" in result.output
    assert "Title" in result.output  # header row


def test_search_no_ai_empty_result(runner, db_session):
    result = runner.invoke(search, ["zzz_no_match_zzz", "--no-ai"])

    assert result.exit_code == 0
    assert "No titles found matching 'zzz_no_match_zzz'." in result.output


# ---------------------------------------------------------------------------
# --films flag
# ---------------------------------------------------------------------------


def test_films_flag_returns_only_movies(runner, db_session):
    _movie(db_session, title="Inception Film", year=2010)
    _show(db_session, title="Inception Show", year=2019)

    result = runner.invoke(search, ["Inception", "--films", "--no-ai"])

    assert result.exit_code == 0
    assert "Inception Film" in result.output
    assert "Inception Show" not in result.output


# ---------------------------------------------------------------------------
# --series flag
# ---------------------------------------------------------------------------


def test_series_flag_returns_only_shows(runner, db_session):
    _movie(db_session, title="Chernobyl Film", year=2019)
    _show(db_session, title="Chernobyl Show", year=2019)

    result = runner.invoke(search, ["Chernobyl", "--series", "--no-ai"])

    assert result.exit_code == 0
    assert "Chernobyl Show" in result.output
    assert "Chernobyl Film" not in result.output


# ---------------------------------------------------------------------------
# --limit
# ---------------------------------------------------------------------------


def test_limit_flag(runner, db_session):
    for i in range(6):
        _movie(db_session, title=f"Film {i}", year=2000 + i)

    result = runner.invoke(search, ["Film", "--no-ai", "--limit", "3"])

    assert result.exit_code == 0
    # Count data rows in the tabulated output (non-header, non-separator)
    data_lines = [
        line for line in result.output.strip().split("\n")
        if line and not line.startswith("Title") and not line.startswith("-")
    ]
    assert len(data_lines) <= 3


# ---------------------------------------------------------------------------
# --no-ai flag
# ---------------------------------------------------------------------------


def test_no_ai_bypasses_agent(runner, db_session):
    """--no-ai must not call _run_with_ai."""
    _movie(db_session, title="Dune", year=2021)

    with patch("file_fetcher.cli.search._run_with_ai") as mock_run_ai:
        result = runner.invoke(search, ["Dune", "--no-ai"])

    mock_run_ai.assert_not_called()
    assert result.exit_code == 0
    assert "Dune" in result.output


# ---------------------------------------------------------------------------
# AI path
# ---------------------------------------------------------------------------


def test_ai_fallback_on_agent_failure(runner, db_session):
    """When _run_with_ai raises unexpectedly, results still displayed from direct DB search."""
    _movie(db_session, title="Blade Runner", year=1982)

    with patch("file_fetcher.cli.search._run_with_ai", side_effect=RuntimeError("AI down")):
        result = runner.invoke(search, ["Blade Runner"])

    # Graceful fallback: exit_code 0 and DB results shown
    assert result.exit_code == 0
    assert "Blade Runner" in result.output


def test_ai_results_reorder_display(runner, db_session):
    """When AI returns reordered titles, display follows AI order."""
    _movie(db_session, title="Alpha", year=2000)
    _movie(db_session, title="Beta", year=2001)

    ai_return = [
        {"title": "Beta", "year": 2001, "media_type": "film",
         "availability": "remote_only", "imdb_rating": "7.0", "genre": "Drama"},
        {"title": "Alpha", "year": 2000, "media_type": "film",
         "availability": "remote_only", "imdb_rating": "6.5", "genre": "Action"},
    ]

    with patch("file_fetcher.cli.search._run_with_ai", return_value=ai_return):
        result = runner.invoke(search, ["a"])

    assert result.exit_code == 0
    output = result.output
    beta_pos = output.find("Beta")
    alpha_pos = output.find("Alpha")
    assert beta_pos < alpha_pos, "Beta (AI rank 1) should appear before Alpha"


# ---------------------------------------------------------------------------
# Tabular format
# ---------------------------------------------------------------------------


def test_tabular_headers_present(runner, db_session):
    _movie(db_session, title="Interstellar", year=2014)

    result = runner.invoke(search, ["Interstellar", "--no-ai"])

    assert "Title" in result.output
    assert "Year" in result.output
    assert "Type" in result.output
    assert "Availability" in result.output
    assert "IMDb" in result.output
    assert "Genre" in result.output


def test_genre_truncated_to_first_value(runner, db_session):
    """Genre column shows only first genre from comma-separated list."""
    m = Movie(
        title="Multi Genre Film",
        year=2020,
        media_type=MediaType.film,
        omdb_status=OmdbStatus.ENRICHED,
    )
    db_session.add(m)
    db_session.flush()
    db_session.add(OmdbData(movie_id=m.id, genre="Action, Comedy, Thriller"))
    db_session.flush()
    rf = RemoteFile(
        movie_id=m.id,
        remote_path="/media/multi.mkv",
        filename="multi.mkv",
        media_type=MediaType.film,
    )
    db_session.add(rf)
    db_session.flush()

    result = runner.invoke(search, ["Multi Genre Film", "--no-ai"])

    assert result.exit_code == 0
    assert "Action" in result.output
    # Full genre string should NOT appear
    assert "Action, Comedy, Thriller" not in result.output
