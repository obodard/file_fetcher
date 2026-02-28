"""Unit tests for cli/delete.py (Story 3.3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_fetcher.models.enums import MediaType
from file_fetcher.models.movie import Movie
from file_fetcher.models.show import Show


def _make_movie(session, title="Inception", year=2010):
    m = Movie(title=title, year=year, media_type=MediaType.film)
    session.add(m)
    session.flush()
    return m


def _make_show(session, title="Chernobyl", year=2019):
    s = Show(title=title, year=year, media_type=MediaType.series)
    session.add(s)
    session.flush()
    return s


# ---------------------------------------------------------------------------
# run_delete — confirm → deletes
# ---------------------------------------------------------------------------

def test_run_delete_movie_on_confirm(db_session):
    """Confirming 'y' deletes the movie."""
    movie = _make_movie(db_session)
    db_session.commit()

    with (
        patch("file_fetcher.cli.delete.get_session") as mock_ctx,
        patch("builtins.input", return_value="y"),
    ):
        mock_ctx.return_value.__enter__ = lambda s: db_session
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        from file_fetcher.cli.delete import run_delete

        run_delete(movie_id=movie.id)

    db_session.commit()
    from file_fetcher.models.movie import Movie as M

    assert db_session.query(M).count() == 0


def test_run_delete_aborts_on_no(db_session):
    """Typing 'n' aborts and leaves the movie intact."""
    movie = _make_movie(db_session)
    db_session.commit()

    with (
        patch("file_fetcher.cli.delete.get_session") as mock_ctx,
        patch("builtins.input", return_value="n"),
        patch("sys.exit") as mock_exit,
    ):
        mock_ctx.return_value.__enter__ = lambda s: db_session
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        from file_fetcher.cli.delete import run_delete

        run_delete(movie_id=movie.id)
        mock_exit.assert_called_once_with(0)


def test_run_delete_movie_not_found_exits(db_session):
    """Providing a non-existent id exits with error."""
    with (
        patch("file_fetcher.cli.delete.get_session") as mock_ctx,
        patch("sys.exit") as mock_exit,
    ):
        mock_ctx.return_value.__enter__ = lambda s: db_session
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        from file_fetcher.cli.delete import run_delete

        run_delete(movie_id=9999)
        mock_exit.assert_called_once_with(1)


# ---------------------------------------------------------------------------
# run_reset
# ---------------------------------------------------------------------------

def test_run_reset_on_exact_confirm(db_session):
    """Typing 'RESET' calls full_reset."""
    with (
        patch("file_fetcher.cli.delete.get_session") as mock_ctx,
        patch("builtins.input", return_value="RESET"),
        patch("file_fetcher.cli.delete.full_reset") as mock_reset,
    ):
        mock_ctx.return_value.__enter__ = lambda s: db_session
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        from file_fetcher.cli.delete import run_reset

        run_reset()
        mock_reset.assert_called_once()


def test_run_reset_aborts_on_wrong_input():
    """Any text other than 'RESET' aborts without calling full_reset."""
    with (
        patch("builtins.input", return_value="reset"),
        patch("file_fetcher.cli.delete.full_reset") as mock_reset,
        patch("sys.exit") as mock_exit,
    ):
        from file_fetcher.cli.delete import run_reset

        run_reset()
        mock_reset.assert_not_called()
        mock_exit.assert_called_once_with(0)
