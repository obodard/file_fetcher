"""Catalog service — queries and aggregates catalog data.

Covers:
  - Story 2.4: get_not_found (movies)
  - Story 2.5: get_not_found extended to include shows
  - Story 3.3: delete_entry, full_reset
"""

from __future__ import annotations

import logging
from typing import NamedTuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from file_fetcher.models.enums import OmdbStatus
from file_fetcher.models.local_file import LocalFile
from file_fetcher.models.movie import Movie
from file_fetcher.models.omdb_data import OmdbData
from file_fetcher.models.remote_file import RemoteFile
from file_fetcher.models.show import Episode, Season, Show

log = logging.getLogger(__name__)


class NotFoundEntry(NamedTuple):
    """A catalog entry with omdb_status == not_found."""

    id: int
    media_kind: str  # "movie" or "show"
    title: str
    year: int | None
    remote_paths: list[str]


def get_not_found(session: Session) -> list[NotFoundEntry]:
    """Return all movies and shows with ``omdb_status == not_found``.

    Each entry includes all associated remote file paths from ``RemoteFile``.
    """
    results: list[NotFoundEntry] = []

    # Movies
    movies = (
        session.query(Movie)
        .filter(Movie.omdb_status == OmdbStatus.NOT_FOUND)
        .order_by(Movie.id)
        .all()
    )
    for movie in movies:
        paths = [
            rf.remote_path
            for rf in session.query(RemoteFile)
            .filter(RemoteFile.movie_id == movie.id)
            .all()
        ]
        results.append(
            NotFoundEntry(
                id=movie.id,
                media_kind="movie",
                title=movie.title,
                year=movie.year,
                remote_paths=paths,
            )
        )

    # Shows
    shows = (
        session.query(Show)
        .filter(Show.omdb_status == OmdbStatus.NOT_FOUND)
        .order_by(Show.id)
        .all()
    )
    for show in shows:
        paths = [
            rf.remote_path
            for rf in session.query(RemoteFile)
            .filter(RemoteFile.show_id == show.id)
            .all()
        ]
        results.append(
            NotFoundEntry(
                id=show.id,
                media_kind="show",
                title=show.title,
                year=show.year,
                remote_paths=paths,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Story 3.3 — deletion helpers
# ---------------------------------------------------------------------------

def delete_entry(
    session: Session,
    movie_id: int | None = None,
    show_id: int | None = None,
) -> None:
    """Delete a movie or show and all its associated child rows.

    Deletion order respects FK constraints: child rows are removed before
    the parent Movie/Show.
    """
    if movie_id is not None:
        # Remove children in FK-safe order
        session.execute(delete(OmdbData).where(OmdbData.movie_id == movie_id))
        session.execute(delete(RemoteFile).where(RemoteFile.movie_id == movie_id))
        session.execute(delete(LocalFile).where(LocalFile.movie_id == movie_id))
        movie = session.get(Movie, movie_id)
        if movie:
            session.delete(movie)
        log.info("Deleted movie id=%s and all associated data.", movie_id)

    elif show_id is not None:
        # Remove episodes → seasons → then the show's other children → show
        season_ids = [
            row[0]
            for row in session.execute(
                select(Season.id).where(Season.show_id == show_id)
            )
        ]
        if season_ids:
            session.execute(delete(Episode).where(Episode.season_id.in_(season_ids)))
        session.execute(delete(Season).where(Season.show_id == show_id))
        session.execute(delete(OmdbData).where(OmdbData.show_id == show_id))
        session.execute(delete(RemoteFile).where(RemoteFile.show_id == show_id))
        session.execute(delete(LocalFile).where(LocalFile.show_id == show_id))
        show = session.get(Show, show_id)
        if show:
            session.delete(show)
        log.info("Deleted show id=%s and all associated data.", show_id)
    else:
        raise ValueError("Provide either movie_id or show_id.")


def full_reset(session: Session) -> None:
    """Delete ALL rows from every catalog table; tables themselves remain.

    Deletion order: child tables first to satisfy FK constraints.
    WARNING logged before execution.
    """
    log.warning("Full database reset executed by user")

    # download_queue may not exist yet (added in Epic 4) — guard gracefully
    try:
        from file_fetcher.models.download_queue import DownloadQueue  # type: ignore
        session.execute(delete(DownloadQueue))
    except (ImportError, Exception):
        pass

    session.execute(delete(LocalFile))
    session.execute(delete(RemoteFile))
    session.execute(delete(OmdbData))
    session.execute(delete(Episode))
    session.execute(delete(Season))
    session.execute(delete(Show))
    session.execute(delete(Movie))
    log.info("Full reset complete.")
