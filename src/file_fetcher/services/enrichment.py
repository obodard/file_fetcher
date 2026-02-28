"""Enrichment service — fetches OMDB metadata and updates catalog entries.

Covers:
  - Story 2.1: enrich_single (movie)
  - Story 2.2: run_enrichment_batch with rate limiting
  - Story 2.3: poster/thumbnail download and storage
  - Story 2.4: force re-enrichment; title/year overrides
  - Story 2.5: enrich_single_show; mixed movie+show batches
"""

from __future__ import annotations

import logging
import os
from io import BytesIO
from typing import Optional

import requests
from sqlalchemy.orm import Session

from file_fetcher.models.enums import OmdbStatus
from file_fetcher.models.movie import Movie
from file_fetcher.models.omdb_data import OmdbData
from file_fetcher.models.show import Show

log = logging.getLogger(__name__)

_OMDB_API_KEY = os.environ.get("OMDB_API_KEY", "")
_OMDB_URL = "https://www.omdbapi.com/"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_api_key() -> str:
    """Return OMDB API key from env (re-read each call to allow test patching)."""
    return os.environ.get("OMDB_API_KEY", _OMDB_API_KEY)


def _fetch_omdb_raw(title: str, year: Optional[int], api_key: str) -> Optional[dict]:
    """Call OMDB and return the full JSON response dict; None on network error.

    Does NOT raise — network/HTTP errors are logged as WARNING and return None.
    """
    if not api_key or api_key in ("your_omdb_api_key", ""):
        log.warning("OMDB_API_KEY is not set; skipping enrichment for '%s'.", title)
        return None
    params: dict = {"t": title, "apikey": api_key}
    if year:
        params["y"] = str(year)
    try:
        resp = requests.get(_OMDB_URL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.warning("OMDB network error for '%s': %s", title, exc)
        return None


def _fetch_omdb_by_id(imdb_id: str, api_key: str) -> Optional[dict]:
    """Call OMDB by direct IMDB ID (e.g. ``"tt1234567"``); None on error.

    Does NOT raise — errors are logged as WARNING and return None.
    """
    if not api_key or api_key in ("your_omdb_api_key", ""):
        log.warning("OMDB_API_KEY is not set; skipping direct-ID enrichment for '%s'.", imdb_id)
        return None
    params: dict = {"i": imdb_id, "apikey": api_key}
    try:
        resp = requests.get(_OMDB_URL, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        log.warning("OMDB network error for IMDB ID '%s': %s", imdb_id, exc)
        return None


def _extract_rating(ratings_list: list[dict], source: str) -> Optional[str]:
    """Extract a rating value by source name from OMDB Ratings list."""
    for entry in ratings_list:
        if entry.get("Source") == source:
            return entry.get("Value")
    return None


def _map_omdb_response(data: dict, omdb: OmdbData) -> None:
    """Populate an OmdbData record from a raw OMDB response dict (in-place)."""
    ratings_list: list[dict] = data.get("Ratings") or []

    omdb.imdb_id = data.get("imdbID") or None
    omdb.title = data.get("Title") or None
    omdb.year = data.get("Year") or None
    omdb.rated = data.get("Rated") or None
    omdb.released = data.get("Released") or None
    omdb.runtime = data.get("Runtime") or None
    omdb.genre = data.get("Genre") or None
    omdb.director = data.get("Director") or None
    omdb.writer = data.get("Writer") or None
    omdb.actors = data.get("Actors") or None
    omdb.plot = data.get("Plot") or None
    omdb.language = data.get("Language") or None
    omdb.country = data.get("Country") or None
    omdb.awards = data.get("Awards") or None
    omdb.imdb_rating = data.get("imdbRating") or None
    omdb.rotten_tomatoes_rating = _extract_rating(ratings_list, "Rotten Tomatoes")
    omdb.metacritic_rating = data.get("Metascore") or None
    omdb.imdb_votes = data.get("imdbVotes") or None
    omdb.box_office = data.get("BoxOffice") or None
    # Poster URL
    poster_raw = data.get("Poster")
    omdb.poster_url = poster_raw if poster_raw and poster_raw != "N/A" else None
    omdb.type = data.get("Type") or None
    omdb.dvd = data.get("DVD") or None
    omdb.production = data.get("Production") or None
    omdb.website = data.get("Website") or None
    # total_seasons — only set for series
    ts = data.get("totalSeasons")
    if ts and str(ts).isdigit():
        omdb.total_seasons = int(ts)
    else:
        omdb.total_seasons = None


def _download_poster(omdb: OmdbData) -> None:
    """Download poster and generate 200 px-wide thumbnail (Story 2.3).

    On any failure: logs WARNING, leaves blobs as NULL. Does NOT fail enrichment.
    """
    if not omdb.poster_url:
        return
    try:
        resp = requests.get(omdb.poster_url, timeout=10)
        resp.raise_for_status()
        poster_bytes = resp.content
        content_type = resp.headers.get("Content-Type", "image/jpeg")
        omdb.poster_blob = poster_bytes
        omdb.poster_content_type = content_type

        # Generate thumbnail
        from PIL import Image  # lazy import — Pillow optional dep catch

        img = Image.open(BytesIO(poster_bytes))
        img.thumbnail((200, 10000))  # preserves aspect ratio, max width 200
        buf = BytesIO()
        fmt = img.format or "JPEG"
        img.save(buf, format=fmt)
        omdb.thumbnail_blob = buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        log.warning("Poster download/thumbnail failed for '%s': %s", omdb.poster_url, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enrich_single(session: Session, movie_id: int, force: bool = False) -> Optional[OmdbData]:
    """Fetch OMDB data for *movie_id* and store in ``OmdbData``.

    Args:
        session:  Active SQLAlchemy session.
        movie_id: PK of the Movie to enrich.
        force:    If True, re-fetch even if already ``enriched`` (Story 2.4).

    Returns:
        The ``OmdbData`` record on success, ``None`` on failure.
    """
    movie: Optional[Movie] = session.get(Movie, movie_id)
    if movie is None:
        log.warning("enrich_single: Movie id=%d not found.", movie_id)
        return None

    if not force and movie.omdb_status == OmdbStatus.ENRICHED:
        log.debug("Movie id=%d already enriched; skipping.", movie_id)
        return movie.omdb_data

    title = movie.title_override or movie.title
    year = movie.year_override or movie.year

    api_key = _get_api_key()
    if movie.override_omdb_id:
        data = _fetch_omdb_by_id(movie.override_omdb_id, api_key)
    else:
        data = _fetch_omdb_raw(title, year, api_key)

    if data is None:
        # Network / HTTP error
        movie.omdb_status = OmdbStatus.FAILED
        return None

    if data.get("Response") == "False":
        movie.omdb_status = OmdbStatus.NOT_FOUND
        return None

    # Upsert OmdbData
    omdb = session.query(OmdbData).filter_by(movie_id=movie_id).first()
    if omdb is None:
        omdb = OmdbData(movie_id=movie_id)
        session.add(omdb)

    _map_omdb_response(data, omdb)
    _download_poster(omdb)
    movie.omdb_status = OmdbStatus.ENRICHED
    session.flush()
    return omdb


def enrich_single_show(session: Session, show_id: int, force: bool = False) -> Optional[OmdbData]:
    """Fetch OMDB data for *show_id* and store in ``OmdbData`` (Story 2.5).

    Args:
        session: Active SQLAlchemy session.
        show_id: PK of the Show to enrich.
        force:   If True, re-fetch even if already ``enriched``.

    Returns:
        The ``OmdbData`` record on success, ``None`` on failure.
    """
    show: Optional[Show] = session.get(Show, show_id)
    if show is None:
        log.warning("enrich_single_show: Show id=%d not found.", show_id)
        return None

    if not force and show.omdb_status == OmdbStatus.ENRICHED:
        log.debug("Show id=%d already enriched; skipping.", show_id)
        return show.omdb_data

    title = show.title_override or show.title
    year = show.year_override or show.year

    api_key = _get_api_key()
    if show.override_omdb_id:
        data = _fetch_omdb_by_id(show.override_omdb_id, api_key)
    else:
        data = _fetch_omdb_raw(title, year, api_key)

    if data is None:
        show.omdb_status = OmdbStatus.FAILED
        return None

    if data.get("Response") == "False":
        show.omdb_status = OmdbStatus.NOT_FOUND
        return None

    omdb = session.query(OmdbData).filter_by(show_id=show_id).first()
    if omdb is None:
        omdb = OmdbData(show_id=show_id)
        session.add(omdb)

    _map_omdb_response(data, omdb)
    _download_poster(omdb)
    show.omdb_status = OmdbStatus.ENRICHED
    session.flush()
    return omdb


def run_enrichment_batch(
    session: Session,
    batch_limit: int = 50,
    daily_quota: int = 900,
) -> dict:
    """Enrich up to *batch_limit* unenriched movies and shows (Stories 2.2, 2.5).

    Stops processing once *daily_quota* API calls have been made in this run.
    Already-enriched entries are never re-processed.

    Returns:
        Dict with keys:
          movies_enriched, movies_not_found, movies_failed,
          shows_enriched, shows_not_found, shows_failed,
          quota_hit (bool), requests_made
    """
    stats = {
        "movies_enriched": 0,
        "movies_not_found": 0,
        "movies_failed": 0,
        "shows_enriched": 0,
        "shows_not_found": 0,
        "shows_failed": 0,
        "quota_hit": False,
        "requests_made": 0,
    }

    # Split batch: half movies, half shows (or full batch each if under limit)
    half = batch_limit // 2
    movie_limit = half if half > 0 else batch_limit
    show_limit = batch_limit - movie_limit

    movies: list[Movie] = (
        session.query(Movie)
        .filter(Movie.omdb_status.in_([OmdbStatus.PENDING, OmdbStatus.FAILED]))
        .order_by(Movie.id)
        .limit(movie_limit)
        .all()
    )

    shows: list[Show] = (
        session.query(Show)
        .filter(Show.omdb_status.in_([OmdbStatus.PENDING, OmdbStatus.FAILED]))
        .order_by(Show.id)
        .limit(show_limit)
        .all()
    )

    total = len(movies) + len(shows)
    processed = 0

    # Process movies
    for movie in movies:
        if stats["requests_made"] >= daily_quota:
            stats["quota_hit"] = True
            log.info(
                "Daily OMDB quota reached (%d/%d). Resuming tomorrow.",
                stats["requests_made"],
                daily_quota,
            )
            break
        if movie.omdb_status == OmdbStatus.ENRICHED:
            continue

        processed += 1
        print(f"[{processed}/{total}] {movie.title} ({movie.year})")

        result = enrich_single(session, movie.id)
        stats["requests_made"] += 1

        if movie.omdb_status == OmdbStatus.ENRICHED:
            stats["movies_enriched"] += 1
        elif movie.omdb_status == OmdbStatus.NOT_FOUND:
            stats["movies_not_found"] += 1
        else:
            stats["movies_failed"] += 1

    # Process shows (continue counting quota from movies)
    if not stats["quota_hit"]:
        for show in shows:
            if stats["requests_made"] >= daily_quota:
                stats["quota_hit"] = True
                log.info(
                    "Daily OMDB quota reached (%d/%d). Resuming tomorrow.",
                    stats["requests_made"],
                    daily_quota,
                )
                break
            if show.omdb_status == OmdbStatus.ENRICHED:
                continue

            processed += 1
            print(f"[{processed}/{total}] {show.title} ({show.year}) [series]")

            enrich_single_show(session, show.id)
            stats["requests_made"] += 1

            if show.omdb_status == OmdbStatus.ENRICHED:
                stats["shows_enriched"] += 1
            elif show.omdb_status == OmdbStatus.NOT_FOUND:
                stats["shows_not_found"] += 1
            else:
                stats["shows_failed"] += 1

    return stats


def enrich_one(session: Session, catalog_id: int) -> tuple[bool, str]:
    """Enrich a catalog entry (movie or show) by numeric ID with ``force=True``.

    Tries the movie table first, then the show table.  Respects
    ``title_override``, ``year_override``, and ``override_omdb_id`` if set.

    Args:
        session:    Active SQLAlchemy session.
        catalog_id: PK to look up in ``movies`` or ``shows``.

    Returns:
        ``(True, "Title (year)")`` on success, or
        ``(False, error_message)`` on failure / not found.
    """
    from file_fetcher.models.movie import Movie  # avoid circular at module level  # noqa: PLC0415
    from file_fetcher.models.show import Show  # noqa: PLC0415

    movie = session.get(Movie, catalog_id)
    if movie is not None:
        result = enrich_single(session, movie.id, force=True)
        if result:
            return True, f"{movie.title} ({movie.year or '?'})"
        return False, movie.omdb_status.value

    show = session.get(Show, catalog_id)
    if show is not None:
        result = enrich_single_show(session, show.id, force=True)
        if result:
            return True, f"{show.title} ({show.year or '?'})"
        return False, show.omdb_status.value

    return False, "Entry not found"
