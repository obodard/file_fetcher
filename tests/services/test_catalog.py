"""Unit tests for catalog.search_catalog and catalog.get_title_detail (Story 5.1)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from file_fetcher.models.base import Base
from file_fetcher.models.download_queue import DownloadQueue
from file_fetcher.models.enums import DownloadStatus, MediaType, OmdbStatus
from file_fetcher.models.local_file import LocalFile
from file_fetcher.models.movie import Movie
from file_fetcher.models.omdb_data import OmdbData
from file_fetcher.models.remote_file import RemoteFile
from file_fetcher.models.show import Show
from file_fetcher.schemas.catalog import CatalogResult, TitleDetail
from file_fetcher.services.catalog import get_title_detail, search_catalog


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


def _movie(
    session: Session,
    title: str = "Inception",
    year: int = 2010,
    omdb_status: OmdbStatus = OmdbStatus.ENRICHED,
    title_override: str | None = None,
) -> Movie:
    m = Movie(
        title=title,
        year=year,
        media_type=MediaType.film,
        omdb_status=omdb_status,
        title_override=title_override,
    )
    session.add(m)
    session.flush()
    return m


def _show(
    session: Session,
    title: str = "Chernobyl",
    year: int = 2019,
    omdb_status: OmdbStatus = OmdbStatus.ENRICHED,
) -> Show:
    s = Show(
        title=title,
        year=year,
        media_type=MediaType.series,
        omdb_status=omdb_status,
    )
    session.add(s)
    session.flush()
    return s


def _omdb(
    session: Session,
    *,
    movie_id: int | None = None,
    show_id: int | None = None,
    genre: str = "Action",
    actors: str = "Leonardo DiCaprio",
    director: str = "Christopher Nolan",
    imdb_rating: str = "8.8",
) -> OmdbData:
    o = OmdbData(
        movie_id=movie_id,
        show_id=show_id,
        genre=genre,
        actors=actors,
        director=director,
        imdb_rating=imdb_rating,
        poster_url="https://example.com/poster.jpg",
    )
    session.add(o)
    session.flush()
    return o


def _remote(
    session: Session,
    path: str = "/media/movies/film.mkv",
    *,
    movie_id: int | None = None,
    show_id: int | None = None,
) -> RemoteFile:
    rf = RemoteFile(
        movie_id=movie_id,
        show_id=show_id,
        remote_path=path,
        filename=path.split("/")[-1],
        media_type=MediaType.film if movie_id else MediaType.series,
    )
    session.add(rf)
    session.flush()
    return rf


def _local(
    session: Session,
    path: str = "/local/movies/film.mkv",
    *,
    movie_id: int | None = None,
    show_id: int | None = None,
) -> LocalFile:
    lf = LocalFile(
        movie_id=movie_id,
        show_id=show_id,
        local_path=path,
        filename=path.split("/")[-1],
        media_type=MediaType.film if movie_id else MediaType.series,
    )
    session.add(lf)
    session.flush()
    return lf


def _queue_entry(
    session: Session,
    remote_file_id: int,
    status: DownloadStatus = DownloadStatus.PENDING,
) -> DownloadQueue:
    dq = DownloadQueue(remote_file_id=remote_file_id, status=status)
    session.add(dq)
    session.flush()
    return dq


# ---------------------------------------------------------------------------
# search_catalog — basic title search
# ---------------------------------------------------------------------------


def test_search_by_title_exact(db_session):
    m = _movie(db_session, title="The Matrix")
    _remote(db_session, movie_id=m.id)

    results = search_catalog(db_session, "Matrix")

    assert len(results) == 1
    assert results[0].title == "The Matrix"
    assert isinstance(results[0], CatalogResult)


def test_search_by_title_case_insensitive(db_session):
    m = _movie(db_session, title="The Matrix")
    _remote(db_session, movie_id=m.id)

    results = search_catalog(db_session, "matrix")

    assert len(results) == 1


def test_search_by_title_override(db_session):
    m = _movie(db_session, title="Unknown Film", title_override="The Matrix Reloaded")
    _remote(db_session, movie_id=m.id)

    results = search_catalog(db_session, "Reloaded")

    assert len(results) == 1
    assert results[0].title == "Unknown Film"


# ---------------------------------------------------------------------------
# search_catalog — enrichment field search
# ---------------------------------------------------------------------------


def test_search_by_genre(db_session):
    m = _movie(db_session, title="Alien")
    _omdb(db_session, movie_id=m.id, genre="Sci-Fi, Horror")

    results = search_catalog(db_session, "Sci-Fi")

    assert len(results) == 1
    assert results[0].title == "Alien"
    assert results[0].genre == "Sci-Fi, Horror"


def test_search_by_actor(db_session):
    m = _movie(db_session, title="Forrest Gump")
    _omdb(db_session, movie_id=m.id, actors="Tom Hanks, Robin Wright")

    results = search_catalog(db_session, "Tom Hanks")

    assert len(results) == 1
    assert results[0].title == "Forrest Gump"


def test_search_by_director(db_session):
    m = _movie(db_session, title="Pulp Fiction")
    _omdb(db_session, movie_id=m.id, director="Quentin Tarantino")

    results = search_catalog(db_session, "Tarantino")

    assert len(results) == 1
    assert results[0].title == "Pulp Fiction"


def test_search_no_match_returns_empty(db_session):
    _movie(db_session, title="Inception")
    results = search_catalog(db_session, "zzz_no_match_zzz")
    assert results == []


# ---------------------------------------------------------------------------
# search_catalog — media_type filter
# ---------------------------------------------------------------------------


def test_media_type_film_returns_only_movies(db_session):
    m = _movie(db_session, title="Inception")
    s = _show(db_session, title="Inception Show")
    _remote(db_session, movie_id=m.id)
    _remote(db_session, path="/media/shows/inception.mkv", show_id=s.id)

    results = search_catalog(db_session, "Inception", media_type="film")

    assert all(r.media_type == "film" for r in results)
    assert len(results) == 1


def test_media_type_series_returns_only_shows(db_session):
    m = _movie(db_session, title="Inception")
    s = _show(db_session, title="Inception Show")
    _remote(db_session, movie_id=m.id)
    _remote(db_session, path="/media/shows/inception.mkv", show_id=s.id)

    results = search_catalog(db_session, "Inception", media_type="series")

    assert all(r.media_type == "series" for r in results)
    assert len(results) == 1


def test_media_type_none_returns_both(db_session):
    m = _movie(db_session, title="Inception")
    s = _show(db_session, title="Inception Show")
    _remote(db_session, movie_id=m.id)
    _remote(db_session, path="/media/shows/inception.mkv", show_id=s.id)

    results = search_catalog(db_session, "Inception", media_type=None)

    types = {r.media_type for r in results}
    assert "film" in types
    assert "series" in types


# ---------------------------------------------------------------------------
# search_catalog — empty query
# ---------------------------------------------------------------------------


def test_empty_query_returns_all(db_session):
    _movie(db_session, title="Film A")
    _movie(db_session, title="Film B")
    _show(db_session, title="Show A")

    results = search_catalog(db_session, "")

    assert len(results) == 3


def test_empty_query_respects_limit(db_session):
    for i in range(10):
        _movie(db_session, title=f"Film {i}", year=2000 + i)

    results = search_catalog(db_session, "", limit=5)

    assert len(results) == 5


# ---------------------------------------------------------------------------
# search_catalog — availability states
# ---------------------------------------------------------------------------


def test_availability_remote_only(db_session):
    m = _movie(db_session, title="Remote Film")
    _remote(db_session, path="/media/remote.mkv", movie_id=m.id)

    results = search_catalog(db_session, "Remote Film")

    assert results[0].availability == "remote_only"
    assert results[0].remote_paths == ["/media/remote.mkv"]
    assert results[0].local_paths == []


def test_availability_in_collection(db_session):
    m = _movie(db_session, title="Local Film")
    _local(db_session, path="/local/local.mkv", movie_id=m.id)

    results = search_catalog(db_session, "Local Film")

    assert results[0].availability == "in_collection"


def test_availability_both(db_session):
    m = _movie(db_session, title="Both Film")
    _remote(db_session, path="/media/both.mkv", movie_id=m.id)
    _local(db_session, path="/local/both.mkv", movie_id=m.id)

    results = search_catalog(db_session, "Both Film")

    assert results[0].availability == "both"


def test_availability_remote_only_downloading(db_session):
    m = _movie(db_session, title="Downloading Film")
    rf = _remote(db_session, path="/media/dl.mkv", movie_id=m.id)
    _queue_entry(db_session, remote_file_id=rf.id, status=DownloadStatus.PENDING)

    results = search_catalog(db_session, "Downloading Film")

    assert results[0].availability == "remote_only_downloading"


def test_availability_downloading_status_downloading(db_session):
    """DownloadStatus.DOWNLOADING also triggers remote_only_downloading."""
    m = _movie(db_session, title="In Progress Film")
    rf = _remote(db_session, path="/media/ip.mkv", movie_id=m.id)
    _queue_entry(db_session, remote_file_id=rf.id, status=DownloadStatus.DOWNLOADING)

    results = search_catalog(db_session, "In Progress Film")

    assert results[0].availability == "remote_only_downloading"


def test_availability_completed_queue_entry_is_remote_only(db_session):
    """A COMPLETED queue entry does NOT make it remote_only_downloading."""
    m = _movie(db_session, title="Completed Film")
    rf = _remote(db_session, path="/media/comp.mkv", movie_id=m.id)
    _queue_entry(db_session, remote_file_id=rf.id, status=DownloadStatus.COMPLETED)

    results = search_catalog(db_session, "Completed Film")

    assert results[0].availability == "remote_only"


# ---------------------------------------------------------------------------
# search_catalog — show availability
# ---------------------------------------------------------------------------


def test_show_availability_remote_only(db_session):
    s = _show(db_session, title="Remote Show")
    _remote(db_session, path="/media/show.mkv", show_id=s.id)

    results = search_catalog(db_session, "Remote Show", media_type="series")

    assert results[0].availability == "remote_only"


# ---------------------------------------------------------------------------
# get_title_detail
# ---------------------------------------------------------------------------


def test_get_title_detail_movie(db_session):
    m = _movie(db_session, title="Interstellar", year=2014)
    rf = _remote(db_session, path="/media/interstellar.mkv", movie_id=m.id)
    _omdb(
        db_session,
        movie_id=m.id,
        genre="Sci-Fi",
        actors="Matthew McConaughey",
        director="Christopher Nolan",
        imdb_rating="8.6",
    )

    detail = get_title_detail(db_session, m.id, "film")

    assert detail is not None
    assert isinstance(detail, TitleDetail)
    assert detail.title == "Interstellar"
    assert detail.year == 2014
    assert detail.media_type == "film"
    assert detail.genre == "Sci-Fi"
    assert detail.imdb_rating == "8.6"
    assert "/media/interstellar.mkv" in detail.remote_paths


def test_get_title_detail_show(db_session):
    s = _show(db_session, title="Breaking Bad", year=2008)
    _remote(db_session, path="/media/bb.mkv", show_id=s.id)
    _omdb(db_session, show_id=s.id, genre="Crime, Drama", actors="Bryan Cranston")

    detail = get_title_detail(db_session, s.id, "series")

    assert detail is not None
    assert detail.title == "Breaking Bad"
    assert detail.media_type == "series"
    assert detail.genre == "Crime, Drama"


def test_get_title_detail_not_found_returns_none(db_session):
    result = get_title_detail(db_session, 9999, "film")
    assert result is None


def test_get_title_detail_no_omdb(db_session):
    m = _movie(db_session, title="No Omdb Film", omdb_status=OmdbStatus.PENDING)

    detail = get_title_detail(db_session, m.id, "film")

    assert detail is not None
    assert detail.genre is None
    assert detail.imdb_rating is None
