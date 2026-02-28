"""Catalog service — queries and aggregates catalog data.

Covers:
  - Story 2.4: get_not_found (movies)
  - Story 2.5: get_not_found extended to include shows
"""

from __future__ import annotations

import logging
from typing import NamedTuple

from sqlalchemy.orm import Session

from file_fetcher.models.enums import OmdbStatus
from file_fetcher.models.movie import Movie
from file_fetcher.models.remote_file import RemoteFile
from file_fetcher.models.show import Show

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
