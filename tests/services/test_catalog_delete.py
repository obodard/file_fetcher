"""Unit tests for catalog.delete_entry and catalog.full_reset (Story 3.3)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from file_fetcher.models.base import Base
from file_fetcher.models.enums import MediaType
from file_fetcher.models.local_file import LocalFile
from file_fetcher.models.movie import Movie
from file_fetcher.models.omdb_data import OmdbData
from file_fetcher.models.remote_file import RemoteFile
from file_fetcher.models.show import Episode, Season, Show
from file_fetcher.services.catalog import delete_entry, full_reset


@pytest.fixture(scope="function")
def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_movie(session: Session, title: str = "Inception", year: int = 2010) -> Movie:
    movie = Movie(title=title, year=year, media_type=MediaType.film)
    session.add(movie)
    session.flush()
    return movie


def _create_show(session: Session, title: str = "Chernobyl", year: int = 2019) -> Show:
    show = Show(title=title, year=year, media_type=MediaType.series)
    session.add(show)
    session.flush()
    return show


def _add_remote_file(session, *, movie_id=None, show_id=None, path="/tmp/f.mkv") -> RemoteFile:
    rf = RemoteFile(
        movie_id=movie_id,
        show_id=show_id,
        remote_path=path,
        filename="f.mkv",
        media_type=MediaType.film if movie_id else MediaType.series,
    )
    session.add(rf)
    session.flush()
    return rf


def _add_local_file(session, *, movie_id=None, show_id=None, path="/local/f.mkv") -> LocalFile:
    lf = LocalFile(
        movie_id=movie_id,
        show_id=show_id,
        local_path=path,
        filename="f.mkv",
        media_type=MediaType.film if movie_id else MediaType.series,
    )
    session.add(lf)
    session.flush()
    return lf


def _add_omdb(session, *, movie_id=None, show_id=None) -> OmdbData:
    omdb = OmdbData(movie_id=movie_id, show_id=show_id)
    session.add(omdb)
    session.flush()
    return omdb


# ---------------------------------------------------------------------------
# delete_entry — movie
# ---------------------------------------------------------------------------

def test_delete_movie_removes_movie_row(db_session):
    """Deleting a movie removes the Movie row."""
    movie = _create_movie(db_session)
    delete_entry(db_session, movie_id=movie.id)
    db_session.commit()

    assert db_session.query(Movie).count() == 0


def test_delete_movie_cascade_remote_file(db_session):
    """Deleting a movie also removes associated RemoteFile rows."""
    movie = _create_movie(db_session)
    _add_remote_file(db_session, movie_id=movie.id, path="/r/f1.mkv")
    _add_remote_file(db_session, movie_id=movie.id, path="/r/f2.mkv")
    delete_entry(db_session, movie_id=movie.id)
    db_session.commit()

    assert db_session.query(RemoteFile).count() == 0


def test_delete_movie_cascade_local_file(db_session):
    """Deleting a movie removes associated LocalFile rows."""
    movie = _create_movie(db_session)
    _add_local_file(db_session, movie_id=movie.id, path="/l/f.mkv")
    delete_entry(db_session, movie_id=movie.id)
    db_session.commit()

    assert db_session.query(LocalFile).count() == 0


def test_delete_movie_cascade_omdb(db_session):
    """Deleting a movie removes associated OmdbData rows."""
    movie = _create_movie(db_session)
    _add_omdb(db_session, movie_id=movie.id)
    delete_entry(db_session, movie_id=movie.id)
    db_session.commit()

    assert db_session.query(OmdbData).count() == 0


# ---------------------------------------------------------------------------
# delete_entry — show (cascade seasons/episodes)
# ---------------------------------------------------------------------------

def test_delete_show_removes_show_row(db_session):
    """Deleting a show removes the Show row."""
    show = _create_show(db_session)
    delete_entry(db_session, show_id=show.id)
    db_session.commit()

    assert db_session.query(Show).count() == 0


def test_delete_show_cascade_seasons_and_episodes(db_session):
    """Deleting a show removes Season and Episode children."""
    show = _create_show(db_session)
    season = Season(show_id=show.id, season_number=1)
    db_session.add(season)
    db_session.flush()
    episode = Episode(season_id=season.id, episode_number=1, title="Pilot")
    db_session.add(episode)
    db_session.flush()

    delete_entry(db_session, show_id=show.id)
    db_session.commit()

    assert db_session.query(Season).count() == 0
    assert db_session.query(Episode).count() == 0


def test_delete_show_cascade_remote_and_local_files(db_session):
    """Deleting a show removes RemoteFile and LocalFile child rows."""
    show = _create_show(db_session)
    _add_remote_file(db_session, show_id=show.id, path="/r/ep.mkv")
    _add_local_file(db_session, show_id=show.id, path="/l/ep.mkv")
    delete_entry(db_session, show_id=show.id)
    db_session.commit()

    assert db_session.query(RemoteFile).count() == 0
    assert db_session.query(LocalFile).count() == 0


def test_delete_entry_raises_without_ids(db_session):
    """delete_entry with no IDs raises ValueError."""
    with pytest.raises(ValueError):
        delete_entry(db_session)


# ---------------------------------------------------------------------------
# full_reset
# ---------------------------------------------------------------------------

def test_full_reset_clears_all_tables(db_session):
    """full_reset removes rows from all catalog tables."""
    movie = _create_movie(db_session)
    _add_remote_file(db_session, movie_id=movie.id, path="/r/m.mkv")
    _add_local_file(db_session, movie_id=movie.id, path="/l/m.mkv")
    _add_omdb(db_session, movie_id=movie.id)
    show = _create_show(db_session)
    season = Season(show_id=show.id, season_number=1)
    db_session.add(season)
    db_session.flush()
    Episode(season_id=season.id, episode_number=1, title="Pilot")

    full_reset(db_session)
    db_session.commit()

    assert db_session.query(Movie).count() == 0
    assert db_session.query(Show).count() == 0
    assert db_session.query(RemoteFile).count() == 0
    assert db_session.query(LocalFile).count() == 0
    assert db_session.query(OmdbData).count() == 0


def test_full_reset_logs_warning(db_session, caplog):
    """full_reset emits a WARNING log."""
    import logging

    with caplog.at_level(logging.WARNING, logger="file_fetcher.services.catalog"):
        full_reset(db_session)

    assert any("Full database reset" in r.message for r in caplog.records)
