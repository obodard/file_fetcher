"""Unit tests for watcher_service (Story 3.1 / 3.2)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from file_fetcher.models.base import Base
from file_fetcher.models.enums import MediaType
from file_fetcher.models.local_file import LocalFile
from file_fetcher.models.movie import Movie
from file_fetcher.models.show import Show
from file_fetcher.services.watcher_service import MediaFileEventHandler, process_new_file


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
# process_new_file — basic cases
# ---------------------------------------------------------------------------

def test_new_film_creates_movie_and_local_file(db_session):
    """A new .mkv film path creates a Movie and a LocalFile."""
    lf = process_new_file(db_session, "/films/Inception.2010.mkv", MediaType.film)
    db_session.commit()

    assert lf is not None
    assert lf.media_type == MediaType.film
    assert lf.filename == "Inception.2010.mkv"

    assert db_session.query(Movie).count() == 1
    assert db_session.query(LocalFile).count() == 1


def test_new_series_creates_show_and_local_file(db_session):
    """A new .mkv series path creates a Show and a LocalFile."""
    lf = process_new_file(db_session, "/series/Breaking.Bad.S01E01.mkv", MediaType.series)
    db_session.commit()

    assert lf is not None
    assert lf.media_type == MediaType.series
    assert db_session.query(Show).count() == 1
    assert db_session.query(LocalFile).count() == 1


def test_existing_movie_reused(db_session):
    """Second file with same title+year reuses the existing Movie row."""
    process_new_file(db_session, "/films/Inception.2010.mkv", MediaType.film)
    db_session.commit()
    lf2 = process_new_file(db_session, "/films/Inception.2010.1080p.mkv", MediaType.film)
    db_session.commit()

    assert lf2 is not None
    # Only one Movie created
    assert db_session.query(Movie).count() == 1
    assert db_session.query(LocalFile).count() == 2


def test_duplicate_local_path_skipped(db_session):
    """Inserting the same local_path twice returns None the second time."""
    process_new_file(db_session, "/films/Inception.2010.mkv", MediaType.film)
    db_session.commit()
    result = process_new_file(db_session, "/films/Inception.2010.mkv", MediaType.film)
    db_session.commit()

    assert result is None
    assert db_session.query(LocalFile).count() == 1


def test_unparseable_filename_logged_and_recorded(db_session, caplog):
    """An unparseable filename (empty title) is recorded with raw name as title."""
    import logging

    with (
        caplog.at_level(logging.WARNING, logger="file_fetcher.services.watcher_service"),
        patch(
            "file_fetcher.services.watcher_service.parse_title_and_year",
            return_value=("", None),
        ),
    ):
        lf = process_new_file(db_session, "/films/bad_file.mkv", MediaType.film)

    db_session.commit()

    # Watcher continues — a LocalFile is created
    assert lf is not None
    assert db_session.query(LocalFile).count() == 1
    # WARNING was emitted
    assert any("Unparseable" in r.message for r in caplog.records)


def test_local_file_fk_linkage_movie(db_session):
    """LocalFile.movie_id is set and points to the correct Movie."""
    lf = process_new_file(db_session, "/films/Dune.2021.mkv", MediaType.film)
    db_session.commit()

    assert lf is not None
    assert lf.movie_id is not None
    movie = db_session.get(Movie, lf.movie_id)
    assert movie is not None
    assert movie.title == "Dune"


def test_local_file_fk_linkage_show(db_session):
    """LocalFile.show_id is set and points to the correct Show."""
    lf = process_new_file(db_session, "/series/Chernobyl.2019.mkv", MediaType.series)
    db_session.commit()

    assert lf is not None
    assert lf.show_id is not None
    show = db_session.get(Show, lf.show_id)
    assert show is not None
    assert show.title == "Chernobyl"


def test_source_directory_stored(db_session):
    """source_directory is persisted on the LocalFile row."""
    lf = process_new_file(
        db_session,
        "/films/Interstellar.2014.mkv",
        MediaType.film,
        source_directory="/films",
    )
    db_session.commit()

    assert lf is not None
    assert lf.source_directory == "/films"


# ---------------------------------------------------------------------------
# MediaFileEventHandler — unit tests via _handle_event
# ---------------------------------------------------------------------------

def _make_event(src_path: str, is_directory: bool = False):
    """Build a minimal watchdog-like event object."""
    return SimpleNamespace(src_path=src_path, is_directory=is_directory)


def test_handler_skips_directories(db_session):
    """Directory events are ignored."""
    session_factory = MagicMock(return_value=db_session)
    handler = MediaFileEventHandler(session_factory, MediaType.film)
    handler._handle_event(_make_event("/films/some_dir", is_directory=True))
    session_factory.assert_not_called()


def test_handler_skips_non_media_extensions(db_session):
    """Non-media extensions (.nfo, .txt…) are ignored."""
    session_factory = MagicMock(return_value=db_session)
    handler = MediaFileEventHandler(session_factory, MediaType.film)
    handler._handle_event(_make_event("/films/readme.txt"))
    session_factory.assert_not_called()


def test_handler_processes_mkv_event(db_session):
    """A .mkv event triggers process_new_file with correct args."""
    with patch(
        "file_fetcher.services.watcher_service.process_new_file",
        return_value=MagicMock(spec=LocalFile),
    ) as mock_pnf:
        mock_session = MagicMock()
        handler = MediaFileEventHandler(
            lambda: mock_session, MediaType.film, source_directory="/films"
        )
        handler._handle_event(_make_event("/films/Inception.2010.mkv"))

    mock_pnf.assert_called_once_with(
        mock_session,
        "/films/Inception.2010.mkv",
        MediaType.film,
        source_directory="/films",
    )
    mock_session.commit.assert_called_once()


def test_handler_continues_after_exception():
    """An error during event processing does not propagate (NFR7)."""
    bad_session = MagicMock()
    bad_session.query.side_effect = RuntimeError("db gone")

    handler = MediaFileEventHandler(lambda: bad_session, MediaType.film)
    # Should NOT raise
    handler._handle_event(_make_event("/films/Inception.2010.mkv"))
