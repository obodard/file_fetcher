"""Watcher service — monitors local directories for new media files.

Covers:
  - Story 3.1: process_new_file, MediaFileEventHandler
  - Story 3.2: source_directory support, error recovery
"""

from __future__ import annotations

import logging
import os
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from file_fetcher.models.enums import MediaType
from file_fetcher.models.local_file import LocalFile
from file_fetcher.models.movie import Movie
from file_fetcher.models.show import Show
from file_fetcher.title_parser import parse_title_and_year

log = logging.getLogger(__name__)

_MEDIA_EXTENSIONS = {".mkv", ".mp4", ".avi", ".m4v"}


def process_new_file(
    session: Session,
    file_path: str,
    media_type: MediaType,
    source_directory: str | None = None,
) -> LocalFile | None:
    """Parse *file_path*, find-or-create a Movie/Show, then insert a LocalFile.

    Returns the created ``LocalFile``, or ``None`` if the path is a duplicate.
    """
    filename = os.path.basename(file_path)

    try:
        title, year = parse_title_and_year(filename)
        if not title:
            raise ValueError("empty title after parsing")
    except Exception:
        log.warning("Unparseable filename %r — recording with raw name as title", filename)
        title = filename
        year = None

    movie_id: int | None = None
    show_id: int | None = None

    if media_type == MediaType.film:
        movie = session.query(Movie).filter_by(title=title, year=year).first()
        if not movie:
            movie = Movie(title=title, year=year, media_type=MediaType.film)
            session.add(movie)
            session.flush()
        movie_id = movie.id
    else:
        show = session.query(Show).filter_by(title=title, year=year).first()
        if not show:
            show = Show(title=title, year=year, media_type=MediaType.series)
            session.add(show)
            session.flush()
        show_id = show.id

    local_file = LocalFile(
        local_path=file_path,
        filename=filename,
        media_type=media_type,
        movie_id=movie_id,
        show_id=show_id,
        source_directory=source_directory,
    )
    session.add(local_file)

    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        log.debug("Duplicate local_path %r — skipped", file_path)
        return None

    return local_file


class MediaFileEventHandler:
    """watchdog FileSystemEventHandler that calls process_new_file on new media files."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        media_type: MediaType,
        source_directory: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._media_type = media_type
        self._source_directory = source_directory

    # Lazily imported so that watchdog is not a hard requirement for tests
    # that mock this class.
    def _get_base_class(self):  # pragma: no cover
        from watchdog.events import FileSystemEventHandler  # type: ignore
        return FileSystemEventHandler

    def on_created(self, event) -> None:  # pragma: no cover — tested via unit tests below
        """Called by watchdog when a new filesystem entry is created."""
        self._handle_event(event)

    def _handle_event(self, event) -> None:
        """Process a watchdog event — separated for testability."""
        if getattr(event, "is_directory", False):
            return

        src_path: str = event.src_path
        _, ext = os.path.splitext(src_path)
        if ext.lower() not in _MEDIA_EXTENSIONS:
            return

        try:
            session = self._session_factory()
            try:
                result = process_new_file(
                    session,
                    src_path,
                    self._media_type,
                    source_directory=self._source_directory,
                )
                if result is not None:
                    session.commit()
                    log.info("Registered new local file: %s", src_path)
            except Exception:
                session.rollback()
                log.error("Error processing new file %r", src_path, exc_info=True)
            finally:
                session.close()
        except Exception:
            log.error("Failed to open DB session for event %r", src_path, exc_info=True)
