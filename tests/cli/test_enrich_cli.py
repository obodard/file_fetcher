"""Tests for CLI commands: enrich, override, not-found.

Covers Stories 2.2, 2.4, 2.5 CLI acceptance criteria.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from file_fetcher.models.base import Base
from file_fetcher.models.enums import OmdbStatus
from file_fetcher.models.movie import Movie
from file_fetcher.models.omdb_data import OmdbData
from file_fetcher.models.show import Show


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def movie(db_session):
    m = Movie(title="Inception", year=2010)
    db_session.add(m)
    db_session.flush()
    return m


@pytest.fixture()
def show(db_session):
    s = Show(title="Westworld", year=2016)
    db_session.add(s)
    db_session.flush()
    return s


# ---------------------------------------------------------------------------
# enrich CLI (Stories 2.2, 2.4, 2.5)
# ---------------------------------------------------------------------------


class TestRunEnrich:
    """Tests for cli/enrich.py run_enrich()."""

    def test_batch_mode_calls_run_enrichment_batch(self, capsys):
        """Default (no --id) calls run_enrichment_batch."""
        mock_stats = {
            "movies_enriched": 3,
            "movies_not_found": 1,
            "movies_failed": 0,
            "shows_enriched": 2,
            "shows_not_found": 0,
            "shows_failed": 0,
            "quota_hit": False,
            "requests_made": 5,
        }

        with (
            patch("file_fetcher.cli.enrich.get_session") as mock_ctx,
            patch("file_fetcher.cli.enrich.run_enrichment_batch", return_value=mock_stats) as mock_batch,
            patch.dict("os.environ", {"OMDB_BATCH_LIMIT": "10", "OMDB_DAILY_QUOTA": "100"}),
        ):
            mock_session = MagicMock()
            mock_ctx.return_value.__enter__ = lambda s: mock_session
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from file_fetcher.cli.enrich import run_enrich

            run_enrich()

        mock_batch.assert_called_once()
        out = capsys.readouterr().out
        assert "enriched" in out

    def test_single_movie_id_calls_enrich_single(self, db_session, movie, capsys):
        """--id <movie_id> calls enrich_single with force=True."""
        mock_omdb = OmdbData(movie_id=movie.id, title="Inception", year="2010")

        with (
            patch("file_fetcher.cli.enrich.get_session") as mock_ctx,
            patch("file_fetcher.cli.enrich.enrich_single", return_value=mock_omdb) as mock_enrich,
        ):
            mock_ctx.return_value.__enter__ = lambda s: db_session
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from file_fetcher.cli.enrich import run_enrich

            run_enrich(movie_id=movie.id)

        mock_enrich.assert_called_once_with(db_session, movie.id, force=True)

    def test_single_show_id_calls_enrich_single_show(self, db_session, show, capsys):
        """--show <show_id> calls enrich_single_show with force=True."""
        mock_omdb = OmdbData(show_id=show.id, title="Westworld", year="2016")

        with (
            patch("file_fetcher.cli.enrich.get_session") as mock_ctx,
            patch("file_fetcher.cli.enrich.enrich_single_show", return_value=mock_omdb) as mock_enrich,
        ):
            mock_ctx.return_value.__enter__ = lambda s: db_session
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from file_fetcher.cli.enrich import run_enrich

            run_enrich(show_id=show.id)

        mock_enrich.assert_called_once_with(db_session, show.id, force=True)

    def test_quota_hit_prints_warning(self, capsys):
        """AC3: quota hit message printed in summary."""
        mock_stats = {
            "movies_enriched": 2,
            "movies_not_found": 0,
            "movies_failed": 0,
            "shows_enriched": 0,
            "shows_not_found": 0,
            "shows_failed": 0,
            "quota_hit": True,
            "requests_made": 3,
        }
        with (
            patch("file_fetcher.cli.enrich.get_session") as mock_ctx,
            patch("file_fetcher.cli.enrich.run_enrichment_batch", return_value=mock_stats),
            patch.dict("os.environ", {"OMDB_DAILY_QUOTA": "3"}),
        ):
            mock_session = MagicMock()
            mock_ctx.return_value.__enter__ = lambda s: mock_session
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from file_fetcher.cli.enrich import run_enrich

            run_enrich()

        out = capsys.readouterr().out
        assert "quota" in out.lower()


# ---------------------------------------------------------------------------
# not-found CLI (Stories 2.4, 2.5)
# ---------------------------------------------------------------------------


class TestRunNotFound:
    """Tests for cli/enrich.py run_not_found()."""

    def test_prints_tabular_report(self, capsys):
        """AC5: not-found entries printed in tabular form."""
        from file_fetcher.services.catalog import NotFoundEntry

        entries = [
            NotFoundEntry(id=1, media_kind="movie", title="Ghost Film", year=2005, remote_paths=["/remote/ghost.mkv"]),
            NotFoundEntry(id=2, media_kind="show", title="Ghost Show", year=2012, remote_paths=[]),
        ]

        with (
            patch("file_fetcher.cli.enrich.get_session") as mock_ctx,
            patch("file_fetcher.cli.enrich.get_not_found", return_value=entries),
        ):
            mock_session = MagicMock()
            mock_ctx.return_value.__enter__ = lambda s: mock_session
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from file_fetcher.cli.enrich import run_not_found

            run_not_found()

        out = capsys.readouterr().out
        assert "Ghost Film" in out
        assert "Ghost Show" in out
        assert "2005" in out

    def test_empty_not_found(self, capsys):
        """Prints no-entries message when list is empty."""
        with (
            patch("file_fetcher.cli.enrich.get_session") as mock_ctx,
            patch("file_fetcher.cli.enrich.get_not_found", return_value=[]),
        ):
            mock_session = MagicMock()
            mock_ctx.return_value.__enter__ = lambda s: mock_session
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from file_fetcher.cli.enrich import run_not_found

            run_not_found()

        out = capsys.readouterr().out
        assert "no" in out.lower() or "empty" in out.lower() or "not_found" in out.lower()


# ---------------------------------------------------------------------------
# override CLI (Stories 2.4, 2.5)
# ---------------------------------------------------------------------------


class TestRunOverride:
    """Tests for cli/override.py run_override()."""

    def test_movie_override_sets_fields(self, db_session, movie):
        """AC3: sets title_override and year_override on movie."""
        with patch("file_fetcher.cli.override.get_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda s: db_session
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from file_fetcher.cli.override import run_override

            run_override(movie_id=movie.id, title="Am\u00e9lie", year=2001)

        assert movie.title_override == "Am\u00e9lie"
        assert movie.year_override == 2001

    def test_show_override_sets_fields(self, db_session, show):
        """AC7/Story 2.5: sets title_override and year_override on show."""
        with patch("file_fetcher.cli.override.get_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda s: db_session
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from file_fetcher.cli.override import run_override

            run_override(show_id=show.id, title="Better Call Saul", year=2015)

        assert show.title_override == "Better Call Saul"
        assert show.year_override == 2015

    def test_movie_not_found_exits(self, db_session):
        """Exits with error when movie_id doesn't exist."""
        with (
            patch("file_fetcher.cli.override.get_session") as mock_ctx,
            pytest.raises(SystemExit) as exc_info,
        ):
            mock_ctx.return_value.__enter__ = lambda s: db_session
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from file_fetcher.cli.override import run_override

            run_override(movie_id=9999, title="Test")

        assert exc_info.value.code == 1

    def test_prints_confirmation(self, db_session, movie, capsys):
        """Confirmation message printed after override."""
        with patch("file_fetcher.cli.override.get_session") as mock_ctx:
            mock_ctx.return_value.__enter__ = lambda s: db_session
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from file_fetcher.cli.override import run_override

            run_override(movie_id=movie.id, title="Am\u00e9lie")

        out = capsys.readouterr().out
        assert "Am\u00e9lie" in out
