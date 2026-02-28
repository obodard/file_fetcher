"""Catalog service — queries and aggregates catalog data.

Covers:
  - Story 2.4: get_not_found (movies)
  - Story 2.5: get_not_found extended to include shows
  - Story 3.3: delete_entry, full_reset
  - Story 5.1: search_catalog, get_title_detail
"""

from __future__ import annotations

import logging
from typing import NamedTuple, Optional

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, contains_eager

from file_fetcher.models.enums import DownloadStatus, OmdbStatus
from file_fetcher.models.local_file import LocalFile
from file_fetcher.models.movie import Movie
from file_fetcher.models.omdb_data import OmdbData
from file_fetcher.models.remote_file import RemoteFile
from file_fetcher.models.show import Episode, Season, Show
from file_fetcher.schemas.catalog import CatalogResult, TitleDetail

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


# ---------------------------------------------------------------------------
# Story 5.1 — search & detail helpers
# ---------------------------------------------------------------------------

def _compute_availability(
    remote_files: list[RemoteFile],
    local_files: list[LocalFile],
    downloading_rf_ids: set[int],
) -> str:
    """Derive availability label from related file collections."""
    has_remote = bool(remote_files)
    has_local = bool(local_files)
    has_downloading = any(rf.id in downloading_rf_ids for rf in remote_files)

    if has_local and has_remote:
        return "both"
    if has_local:
        return "in_collection"
    if has_remote and has_downloading:
        return "remote_only_downloading"
    if has_remote:
        return "remote_only"
    return "remote_only"


def _load_downloading_rf_ids(session: Session, rf_ids: list[int]) -> set[int]:
    """Return remote_file_ids that have a pending/downloading DownloadQueue entry."""
    if not rf_ids:
        return set()
    try:
        from file_fetcher.models.download_queue import DownloadQueue  # noqa: PLC0415

        entries = (
            session.query(DownloadQueue)
            .filter(
                DownloadQueue.remote_file_id.in_(rf_ids),
                DownloadQueue.status.in_(
                    [DownloadStatus.PENDING, DownloadStatus.DOWNLOADING]
                ),
            )
            .all()
        )
        return {dq.remote_file_id for dq in entries}
    except Exception:  # noqa: BLE001
        return set()


def _build_catalog_results_for_movies(
    session: Session,
    movies: list[Movie],
    downloading_rf_ids: set[int],
) -> list[CatalogResult]:
    """Map a list of Movie ORM objects to CatalogResult schemas."""
    movie_ids = [m.id for m in movies]

    remote_by_movie: dict[int, list[RemoteFile]] = {}
    local_by_movie: dict[int, list[LocalFile]] = {}

    if movie_ids:
        for rf in session.query(RemoteFile).filter(RemoteFile.movie_id.in_(movie_ids)):
            remote_by_movie.setdefault(rf.movie_id, []).append(rf)
        for lf in session.query(LocalFile).filter(LocalFile.movie_id.in_(movie_ids)):
            local_by_movie.setdefault(lf.movie_id, []).append(lf)

    results: list[CatalogResult] = []
    for movie in movies:
        rfs = remote_by_movie.get(movie.id, [])
        lfs = local_by_movie.get(movie.id, [])
        omdb = movie.omdb_data
        results.append(
            CatalogResult(
                id=movie.id,
                title=movie.title,
                year=movie.year,
                media_type=movie.media_type.value,
                omdb_status=movie.omdb_status.value,
                availability=_compute_availability(rfs, lfs, downloading_rf_ids),
                remote_paths=[rf.remote_path for rf in rfs],
                local_paths=[lf.local_path for lf in lfs],
                genre=omdb.genre if omdb else None,
                director=omdb.director if omdb else None,
                actors=omdb.actors if omdb else None,
                imdb_rating=omdb.imdb_rating if omdb else None,
                poster_url=omdb.poster_url if omdb else None,
            )
        )
    return results


def _build_catalog_results_for_shows(
    session: Session,
    shows: list[Show],
    downloading_rf_ids: set[int],
) -> list[CatalogResult]:
    """Map a list of Show ORM objects to CatalogResult schemas."""
    show_ids = [s.id for s in shows]

    remote_by_show: dict[int, list[RemoteFile]] = {}
    local_by_show: dict[int, list[LocalFile]] = {}

    if show_ids:
        for rf in session.query(RemoteFile).filter(RemoteFile.show_id.in_(show_ids)):
            remote_by_show.setdefault(rf.show_id, []).append(rf)
        for lf in session.query(LocalFile).filter(LocalFile.show_id.in_(show_ids)):
            local_by_show.setdefault(lf.show_id, []).append(lf)

    results: list[CatalogResult] = []
    for show in shows:
        rfs = remote_by_show.get(show.id, [])
        lfs = local_by_show.get(show.id, [])
        omdb = show.omdb_data
        results.append(
            CatalogResult(
                id=show.id,
                title=show.title,
                year=show.year,
                media_type=show.media_type.value,
                omdb_status=show.omdb_status.value,
                availability=_compute_availability(rfs, lfs, downloading_rf_ids),
                remote_paths=[rf.remote_path for rf in rfs],
                local_paths=[lf.local_path for lf in lfs],
                genre=omdb.genre if omdb else None,
                director=omdb.director if omdb else None,
                actors=omdb.actors if omdb else None,
                imdb_rating=omdb.imdb_rating if omdb else None,
                poster_url=omdb.poster_url if omdb else None,
            )
        )
    return results


def search_catalog(
    session: Session,
    query: str,
    media_type: Optional[str] = None,
    limit: int = 100,
) -> list[CatalogResult]:
    """Search the catalog by title, genre, actor, or director.

    Performs case-insensitive matching across ``Movie`` and ``Show`` tables,
    joined to ``OmdbData`` for richer filtering.

    Args:
        session: Active SQLAlchemy session.
        query: Free-text search string.  Empty string → return all entries.
        media_type: ``"film"`` for movies only, ``"series"`` for shows only,
            ``None`` for both.
        limit: Maximum number of results to return (default 100).

    Returns:
        List of :class:`CatalogResult` Pydantic instances.
    """
    results: list[CatalogResult] = []
    pattern = f"%{query}%"
    downloading_rf_ids: set[int] = set()  # populated lazily after collecting all rf ids

    include_movies = media_type in (None, "film")
    include_shows = media_type in (None, "series")

    # ── Movies ────────────────────────────────────────────────────────────
    movies: list[Movie] = []
    if include_movies:
        movie_q = (
            session.query(Movie)
            .outerjoin(OmdbData, OmdbData.movie_id == Movie.id)
            .options(contains_eager(Movie.omdb_data))
        )
        if query:
            movie_q = movie_q.filter(
                or_(
                    Movie.title.ilike(pattern),
                    Movie.title_override.ilike(pattern),
                    OmdbData.genre.ilike(pattern),
                    OmdbData.actors.ilike(pattern),
                    OmdbData.director.ilike(pattern),
                )
            )
        movies = movie_q.limit(limit).all()

    # ── Shows ─────────────────────────────────────────────────────────────
    shows: list[Show] = []
    if include_shows:
        show_q = (
            session.query(Show)
            .outerjoin(OmdbData, OmdbData.show_id == Show.id)
            .options(contains_eager(Show.omdb_data))
        )
        if query:
            show_q = show_q.filter(
                or_(
                    Show.title.ilike(pattern),
                    Show.title_override.ilike(pattern),
                    OmdbData.genre.ilike(pattern),
                    OmdbData.actors.ilike(pattern),
                    OmdbData.director.ilike(pattern),
                )
            )
        shows = show_q.limit(limit).all()

    # ── Batch-load RemoteFiles to check DownloadQueue ─────────────────────
    movie_ids = [m.id for m in movies]
    show_ids = [s.id for s in shows]

    rf_id_list: list[int] = []
    if movie_ids:
        rf_id_list += [
            row[0]
            for row in session.execute(
                select(RemoteFile.id).where(RemoteFile.movie_id.in_(movie_ids))
            )
        ]
    if show_ids:
        rf_id_list += [
            row[0]
            for row in session.execute(
                select(RemoteFile.id).where(RemoteFile.show_id.in_(show_ids))
            )
        ]

    if rf_id_list:
        downloading_rf_ids = _load_downloading_rf_ids(session, rf_id_list)

    # ── Map to schemas ────────────────────────────────────────────────────
    results.extend(_build_catalog_results_for_movies(session, movies, downloading_rf_ids))
    results.extend(_build_catalog_results_for_shows(session, shows, downloading_rf_ids))

    return results[:limit]


def get_title_detail(
    session: Session,
    title_id: int,
    media_type: str,
) -> Optional[TitleDetail]:
    """Return full detail for a single catalog entry.

    Args:
        session: Active SQLAlchemy session.
        title_id: Primary key of the movie or show.
        media_type: ``"film"`` for movies, ``"series"`` for shows.

    Returns:
        :class:`TitleDetail` or ``None`` if not found.
    """
    if media_type == "film":
        entry = (
            session.query(Movie)
            .outerjoin(OmdbData, OmdbData.movie_id == Movie.id)
            .options(contains_eager(Movie.omdb_data))
            .filter(Movie.id == title_id)
            .first()
        )
        if entry is None:
            return None

        rfs = session.query(RemoteFile).filter(RemoteFile.movie_id == title_id).all()
        lfs = session.query(LocalFile).filter(LocalFile.movie_id == title_id).all()
        rf_ids = [rf.id for rf in rfs]
        downloading = _load_downloading_rf_ids(session, rf_ids)
        omdb = entry.omdb_data

        return TitleDetail(
            id=entry.id,
            title=entry.title,
            year=entry.year,
            media_type=entry.media_type.value,
            omdb_status=entry.omdb_status.value,
            availability=_compute_availability(rfs, lfs, downloading),
            remote_paths=[rf.remote_path for rf in rfs],
            local_paths=[lf.local_path for lf in lfs],
            imdb_id=omdb.imdb_id if omdb else None,
            imdb_rating=omdb.imdb_rating if omdb else None,
            rotten_tomatoes_rating=omdb.rotten_tomatoes_rating if omdb else None,
            metacritic_rating=omdb.metacritic_rating if omdb else None,
            genre=omdb.genre if omdb else None,
            director=omdb.director if omdb else None,
            writer=omdb.writer if omdb else None,
            actors=omdb.actors if omdb else None,
            plot=omdb.plot if omdb else None,
            language=omdb.language if omdb else None,
            country=omdb.country if omdb else None,
            awards=omdb.awards if omdb else None,
            rated=omdb.rated if omdb else None,
            released=omdb.released if omdb else None,
            runtime=omdb.runtime if omdb else None,
            poster_url=omdb.poster_url if omdb else None,
            total_seasons=omdb.total_seasons if omdb else None,
            imdb_votes=omdb.imdb_votes if omdb else None,
            box_office=omdb.box_office if omdb else None,
        )

    else:  # series
        entry = (
            session.query(Show)
            .outerjoin(OmdbData, OmdbData.show_id == Show.id)
            .options(contains_eager(Show.omdb_data))
            .filter(Show.id == title_id)
            .first()
        )
        if entry is None:
            return None

        rfs = session.query(RemoteFile).filter(RemoteFile.show_id == title_id).all()
        lfs = session.query(LocalFile).filter(LocalFile.show_id == title_id).all()
        rf_ids = [rf.id for rf in rfs]
        downloading = _load_downloading_rf_ids(session, rf_ids)
        omdb = entry.omdb_data

        return TitleDetail(
            id=entry.id,
            title=entry.title,
            year=entry.year,
            media_type=entry.media_type.value,
            omdb_status=entry.omdb_status.value,
            availability=_compute_availability(rfs, lfs, downloading),
            remote_paths=[rf.remote_path for rf in rfs],
            local_paths=[lf.local_path for lf in lfs],
            imdb_id=omdb.imdb_id if omdb else None,
            imdb_rating=omdb.imdb_rating if omdb else None,
            rotten_tomatoes_rating=omdb.rotten_tomatoes_rating if omdb else None,
            metacritic_rating=omdb.metacritic_rating if omdb else None,
            genre=omdb.genre if omdb else None,
            director=omdb.director if omdb else None,
            writer=omdb.writer if omdb else None,
            actors=omdb.actors if omdb else None,
            plot=omdb.plot if omdb else None,
            language=omdb.language if omdb else None,
            country=omdb.country if omdb else None,
            awards=omdb.awards if omdb else None,
            rated=omdb.rated if omdb else None,
            released=omdb.released if omdb else None,
            runtime=omdb.runtime if omdb else None,
            poster_url=omdb.poster_url if omdb else None,
            total_seasons=omdb.total_seasons if omdb else None,
            imdb_votes=omdb.imdb_votes if omdb else None,
            box_office=omdb.box_office if omdb else None,
        )

