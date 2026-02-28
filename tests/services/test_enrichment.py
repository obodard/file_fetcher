"""Tests for services/enrichment.py.

Covers Stories 2.1, 2.2, 2.3, 2.4, 2.5.
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from file_fetcher.models.base import Base
from file_fetcher.models.enums import OmdbStatus
from file_fetcher.models.movie import Movie
from file_fetcher.models.omdb_data import OmdbData
from file_fetcher.models.show import Show


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
    m = Movie(title="The Matrix", year=1999)
    db_session.add(m)
    db_session.flush()
    return m


@pytest.fixture()
def show(db_session):
    s = Show(title="Breaking Bad", year=2008)
    db_session.add(s)
    db_session.flush()
    return s


OMDB_SUCCESS = {
    "Response": "True",
    "imdbID": "tt0133093",
    "Title": "The Matrix",
    "Year": "1999",
    "Rated": "R",
    "Released": "31 Mar 1999",
    "Runtime": "136 min",
    "Genre": "Action, Sci-Fi",
    "Director": "The Wachowskis",
    "Writer": "Lilly Wachowski, Lana Wachowski",
    "Actors": "Keanu Reeves, Laurence Fishburne",
    "Plot": "A hacker discovers the true nature of the world.",
    "Language": "English",
    "Country": "USA, Australia",
    "Awards": "4 wins",
    "imdbRating": "8.7",
    "Ratings": [
        {"Source": "Internet Movie Database", "Value": "8.7/10"},
        {"Source": "Rotten Tomatoes", "Value": "88%"},
        {"Source": "Metacritic", "Value": "73/100"},
    ],
    "Metascore": "73",
    "imdbVotes": "2,000,000",
    "BoxOffice": "$171,479,930",
    "Poster": "https://example.com/poster.jpg",
    "Type": "movie",
    "DVD": "21 Sep 1999",
    "Production": "Warner Bros.",
    "Website": "N/A",
    "totalSeasons": None,
}

OMDB_NOT_FOUND = {
    "Response": "False",
    "Error": "Movie not found!",
}

OMDB_SHOW = dict(OMDB_SUCCESS, Title="Breaking Bad", imdbID="tt0903747", Type="series", totalSeasons="5")


def _mock_response(data: dict):
    """Return a MagicMock that looks like a requests.Response with .json()."""
    resp = MagicMock()
    resp.json.return_value = data
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# Story 2.1: enrich_single — basic enrichment
# ---------------------------------------------------------------------------


class TestEnrichSingle:
    """Tests for enrich_single() — Story 2.1."""

    def test_successful_enrichment(self, db_session, movie):
        """AC4: successful enrichment creates OmdbData and sets status=enriched."""
        with patch("file_fetcher.services.enrichment.requests.get") as mock_get:
            mock_get.return_value = _mock_response(OMDB_SUCCESS)
            # Prevent actual poster download
            mock_get.side_effect = [
                _mock_response(OMDB_SUCCESS),  # OMDB call
                Exception("no poster download in this test"),  # poster call fails gracefully
            ]

            from file_fetcher.services.enrichment import enrich_single

            # Ensure API key is set
            with patch.dict("os.environ", {"OMDB_API_KEY": "testkey"}):
                result = enrich_single(db_session, movie.id)

        assert result is not None
        assert result.imdb_id == "tt0133093"
        assert result.title == "The Matrix"
        assert result.rotten_tomatoes_rating == "88%"
        assert result.metacritic_rating == "73"
        assert movie.omdb_status == OmdbStatus.ENRICHED

    def test_not_found(self, db_session, movie):
        """AC5: OMDB Response=False sets status=not_found."""
        with patch("file_fetcher.services.enrichment.requests.get", return_value=_mock_response(OMDB_NOT_FOUND)):
            with patch.dict("os.environ", {"OMDB_API_KEY": "testkey"}):
                from file_fetcher.services.enrichment import enrich_single

                result = enrich_single(db_session, movie.id)

        assert result is None
        assert movie.omdb_status == OmdbStatus.NOT_FOUND

    def test_api_network_failure(self, db_session, movie):
        """AC6: Network error sets status=failed, returns None."""
        import requests as req_module

        with patch(
            "file_fetcher.services.enrichment.requests.get",
            side_effect=req_module.RequestException("timeout"),
        ):
            with patch.dict("os.environ", {"OMDB_API_KEY": "testkey"}):
                from file_fetcher.services.enrichment import enrich_single

                result = enrich_single(db_session, movie.id)

        assert result is None
        assert movie.omdb_status == OmdbStatus.FAILED

    def test_title_override_used(self, db_session, movie):
        """AC4/Story2.4 AC1: title_override and year_override are used when set."""
        movie.title_override = "Amélie"
        movie.year_override = 2001
        db_session.flush()

        captured_params = {}

        def fake_get(url, params=None, timeout=None):
            captured_params.update(params or {})
            return _mock_response(OMDB_SUCCESS)

        with (
            patch("file_fetcher.services.enrichment.requests.get", side_effect=fake_get),
            patch("file_fetcher.services.enrichment._download_poster"),
        ):
            with patch.dict("os.environ", {"OMDB_API_KEY": "testkey"}):
                from file_fetcher.services.enrichment import enrich_single

                enrich_single(db_session, movie.id)

        assert captured_params.get("t") == "Amélie"
        assert captured_params.get("y") == "2001"

    def test_upsert_existing_omdb_data(self, db_session, movie):
        """Story 2.4 AC2: force=True re-fetches and updates existing OmdbData."""
        # Create initial OmdbData
        old_omdb = OmdbData(movie_id=movie.id, title="Old Title", imdb_id="old")
        db_session.add(old_omdb)
        movie.omdb_status = OmdbStatus.ENRICHED
        db_session.flush()

        with patch("file_fetcher.services.enrichment.requests.get") as mock_get:
            mock_get.side_effect = [
                _mock_response(OMDB_SUCCESS),  # OMDB call
                Exception("skip poster"),  # poster download fails
            ]
            with patch.dict("os.environ", {"OMDB_API_KEY": "testkey"}):
                from file_fetcher.services.enrichment import enrich_single

                result = enrich_single(db_session, movie.id, force=True)

        assert result is not None
        assert result.imdb_id == "tt0133093"
        assert result.title == "The Matrix"
        # Should be the same record, updated
        count = db_session.query(OmdbData).filter_by(movie_id=movie.id).count()
        assert count == 1

    def test_skip_already_enriched(self, db_session, movie):
        """force=False skips already-enriched movies."""
        movie.omdb_status = OmdbStatus.ENRICHED
        omdb = OmdbData(movie_id=movie.id, title="The Matrix")
        db_session.add(omdb)
        db_session.flush()

        with patch("file_fetcher.services.enrichment.requests.get") as mock_get:
            from file_fetcher.services.enrichment import enrich_single

            result = enrich_single(db_session, movie.id, force=False)

        # Should not have called OMDB
        mock_get.assert_not_called()
        assert result is not None  # returns existing OmdbData

    def test_movie_not_found_in_db(self, db_session):
        """Returns None if movie_id doesn't exist."""
        from file_fetcher.services.enrichment import enrich_single

        result = enrich_single(db_session, 9999)
        assert result is None


# ---------------------------------------------------------------------------
# Story 2.2: run_enrichment_batch
# ---------------------------------------------------------------------------


class TestRunEnrichmentBatch:
    """Tests for run_enrichment_batch() — Story 2.2."""

    def _make_movies(self, db_session, count: int) -> list[Movie]:
        movies = []
        for i in range(count):
            m = Movie(title=f"Movie {i}", year=2000 + i)
            db_session.add(m)
            movies.append(m)
        db_session.flush()
        return movies

    def test_batch_limit_respected(self, db_session):
        """AC1: only batch_limit entries are processed."""
        self._make_movies(db_session, 10)

        call_count = 0

        def fake_enrich(session, movie_id, force=False):
            nonlocal call_count
            call_count += 1
            movie = session.get(Movie, movie_id)
            if movie:
                movie.omdb_status = OmdbStatus.ENRICHED
                omdb = OmdbData(movie_id=movie.id, title=movie.title)
                session.add(omdb)
                session.flush()
            return omdb

        with patch("file_fetcher.services.enrichment.enrich_single", side_effect=fake_enrich):
            from file_fetcher.services.enrichment import run_enrichment_batch

            stats = run_enrichment_batch(db_session, batch_limit=4, daily_quota=900)

        assert stats["requests_made"] <= 4
        assert stats["movies_enriched"] <= 4

    def test_quota_enforcement(self, db_session):
        """AC3: stops when daily_quota is reached."""
        self._make_movies(db_session, 20)

        call_count = 0

        def fake_enrich(session, movie_id, force=False):
            nonlocal call_count
            call_count += 1
            movie = session.get(Movie, movie_id)
            if movie:
                movie.omdb_status = OmdbStatus.ENRICHED
                omdb = OmdbData(movie_id=movie.id, title=movie.title)
                session.add(omdb)
                session.flush()
            return omdb

        with patch("file_fetcher.services.enrichment.enrich_single", side_effect=fake_enrich):
            from file_fetcher.services.enrichment import run_enrichment_batch

            stats = run_enrichment_batch(db_session, batch_limit=50, daily_quota=3)

        assert stats["quota_hit"] is True
        assert stats["requests_made"] >= 3

    def test_skip_already_enriched_in_query(self, db_session):
        """AC2: already-enriched entries do not appear in batch query."""
        m_enriched = Movie(title="Already Done", year=2000)
        m_pending = Movie(title="Needs Enrichment", year=2001)
        db_session.add_all([m_enriched, m_pending])
        db_session.flush()
        m_enriched.omdb_status = OmdbStatus.ENRICHED
        db_session.flush()

        processed_ids = []

        def fake_enrich(session, movie_id, force=False):
            processed_ids.append(movie_id)
            movie = session.get(Movie, movie_id)
            if movie:
                movie.omdb_status = OmdbStatus.ENRICHED
                omdb = OmdbData(movie_id=movie.id, title=movie.title)
                session.add(omdb)
                session.flush()
            return omdb

        with patch("file_fetcher.services.enrichment.enrich_single", side_effect=fake_enrich):
            from file_fetcher.services.enrichment import run_enrichment_batch

            run_enrichment_batch(db_session, batch_limit=50, daily_quota=900)

        # Only the pending movie should be processed
        assert m_enriched.id not in processed_ids
        assert m_pending.id in processed_ids

    def test_resume_after_interruption(self, db_session):
        """AC4: previously processed entries are not re-processed on second run."""
        movies = self._make_movies(db_session, 5)

        enriched_ids = set()

        def fake_enrich(session, movie_id, force=False):
            enriched_ids.add(movie_id)
            movie = session.get(Movie, movie_id)
            if movie:
                movie.omdb_status = OmdbStatus.ENRICHED
                omdb = OmdbData(movie_id=movie.id, title=movie.title)
                session.add(omdb)
                session.flush()
            return omdb

        with patch("file_fetcher.services.enrichment.enrich_single", side_effect=fake_enrich):
            from file_fetcher.services.enrichment import run_enrichment_batch

            # First run: processes 3
            run_enrichment_batch(db_session, batch_limit=3, daily_quota=900)
            first_run_count = len(enriched_ids)

            # Second run: should pick up remaining 2 (not the already-enriched 3)
            enriched_ids.clear()
            run_enrichment_batch(db_session, batch_limit=50, daily_quota=900)
            second_run_count = len(enriched_ids)

        assert first_run_count <= 3
        # Second run should not re-process the first batch
        assert second_run_count <= 5 - first_run_count


# ---------------------------------------------------------------------------
# Story 2.3: poster download and thumbnail
# ---------------------------------------------------------------------------


class TestPosterDownload:
    """Tests for poster download and thumbnail generation — Story 2.3."""

    def _make_jpeg_bytes(self, width: int = 400, height: int = 600) -> bytes:
        """Create minimal JPEG bytes using Pillow."""
        from PIL import Image

        img = Image.new("RGB", (width, height), color=(100, 150, 200))
        buf = BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()

    def test_poster_download_and_thumbnail(self, db_session, movie):
        """AC2: poster downloaded, thumbnail generated at 200px width."""
        jpeg_bytes = self._make_jpeg_bytes(400, 600)

        omdb = OmdbData(movie_id=movie.id, poster_url="https://example.com/poster.jpg")
        db_session.add(omdb)
        db_session.flush()

        poster_resp = MagicMock()
        poster_resp.raise_for_status.return_value = None
        poster_resp.content = jpeg_bytes
        poster_resp.headers = {"Content-Type": "image/jpeg"}

        with patch("file_fetcher.services.enrichment.requests.get", return_value=poster_resp):
            from file_fetcher.services.enrichment import _download_poster

            _download_poster(omdb)

        assert omdb.poster_blob == jpeg_bytes
        assert omdb.poster_content_type == "image/jpeg"
        assert omdb.thumbnail_blob is not None

        # Verify thumbnail width is ≤ 200
        from PIL import Image

        thumb = Image.open(BytesIO(omdb.thumbnail_blob))
        assert thumb.width <= 200

    def test_na_poster_skipped(self, db_session, movie):
        """AC3: no download attempted when poster_url is None (N/A case)."""
        omdb = OmdbData(movie_id=movie.id, poster_url=None)
        db_session.add(omdb)
        db_session.flush()

        with patch("file_fetcher.services.enrichment.requests.get") as mock_get:
            from file_fetcher.services.enrichment import _download_poster

            _download_poster(omdb)
            mock_get.assert_not_called()

        assert omdb.poster_blob is None
        assert omdb.thumbnail_blob is None

    def test_download_failure_does_not_fail_enrichment(self, db_session, movie):
        """AC4: poster download exception → blobs stay NULL, no exception raised."""
        import requests as req_module

        omdb = OmdbData(movie_id=movie.id, poster_url="https://example.com/fail.jpg")
        db_session.add(omdb)
        db_session.flush()

        with patch(
            "file_fetcher.services.enrichment.requests.get",
            side_effect=req_module.RequestException("timeout"),
        ):
            from file_fetcher.services.enrichment import _download_poster

            # Should not raise
            _download_poster(omdb)

        assert omdb.poster_blob is None
        assert omdb.thumbnail_blob is None

    def test_poster_url_na_string_not_stored(self, db_session, movie):
        """OMDB 'N/A' poster string → poster_url stored as None."""
        data = dict(OMDB_SUCCESS, Poster="N/A")

        omdb = OmdbData(movie_id=movie.id)

        from file_fetcher.services.enrichment import _map_omdb_response

        _map_omdb_response(data, omdb)
        assert omdb.poster_url is None


# ---------------------------------------------------------------------------
# Story 2.4: override + not_found + re-enrichment
# ---------------------------------------------------------------------------


class TestOverrideReEnrichment:
    """Tests for title override, re-enrichment, not_found — Story 2.4."""

    def test_force_reenrichment(self, db_session, movie):
        """AC2: force=True re-fetches even for enriched movies."""
        movie.omdb_status = OmdbStatus.ENRICHED
        old_omdb = OmdbData(movie_id=movie.id, title="Old", imdb_id="old")
        db_session.add(old_omdb)
        db_session.flush()

        with patch("file_fetcher.services.enrichment.requests.get") as mock_get:
            mock_get.side_effect = [
                _mock_response(OMDB_SUCCESS),
                Exception("skip poster"),
            ]
            with patch.dict("os.environ", {"OMDB_API_KEY": "testkey"}):
                from file_fetcher.services.enrichment import enrich_single

                result = enrich_single(db_session, movie.id, force=True)

        assert result is not None
        assert result.title == "The Matrix"
        assert movie.omdb_status == OmdbStatus.ENRICHED


# ---------------------------------------------------------------------------
# Story 2.5: show-level enrichment
# ---------------------------------------------------------------------------


class TestShowEnrichment:
    """Tests for show-level enrichment — Story 2.5."""

    def test_enrich_single_show_success(self, db_session, show):
        """AC4: show enriched, OmdbData linked via show_id."""
        with patch("file_fetcher.services.enrichment.requests.get") as mock_get:
            mock_get.side_effect = [
                _mock_response(OMDB_SHOW),  # OMDB call
                Exception("skip poster"),  # poster
            ]
            with patch.dict("os.environ", {"OMDB_API_KEY": "testkey"}):
                from file_fetcher.services.enrichment import enrich_single_show

                result = enrich_single_show(db_session, show.id)

        assert result is not None
        assert result.show_id == show.id
        assert result.movie_id is None
        assert result.imdb_id == "tt0903747"
        assert show.omdb_status == OmdbStatus.ENRICHED

    def test_enrich_single_show_not_found(self, db_session, show):
        """Show not found → status=not_found, return None."""
        with patch(
            "file_fetcher.services.enrichment.requests.get",
            return_value=_mock_response(OMDB_NOT_FOUND),
        ):
            with patch.dict("os.environ", {"OMDB_API_KEY": "testkey"}):
                from file_fetcher.services.enrichment import enrich_single_show

                result = enrich_single_show(db_session, show.id)

        assert result is None
        assert show.omdb_status == OmdbStatus.NOT_FOUND

    def test_show_override_used(self, db_session, show):
        """Show title_override and year_override are used."""
        show.title_override = "Better Call Saul"
        show.year_override = 2015
        db_session.flush()

        captured = {}

        def fake_get(url, params=None, timeout=None):
            captured.update(params or {})
            return _mock_response(OMDB_SHOW)

        with (
            patch("file_fetcher.services.enrichment.requests.get", side_effect=fake_get),
            patch("file_fetcher.services.enrichment._download_poster"),
        ):
            with patch.dict("os.environ", {"OMDB_API_KEY": "testkey"}):
                from file_fetcher.services.enrichment import enrich_single_show

                enrich_single_show(db_session, show.id)

        assert captured.get("t") == "Better Call Saul"
        assert captured.get("y") == "2015"

    def test_mixed_batch_movies_and_shows(self, db_session):
        """AC3/Story2.5 AC8: batch processes both movies and shows."""
        m = Movie(title="Some Film", year=2020)
        s = Show(title="Some Show", year=2021)
        db_session.add_all([m, s])
        db_session.flush()

        movie_ids_processed = []
        show_ids_processed = []

        def fake_enrich_movie(session, movie_id, force=False):
            movie_ids_processed.append(movie_id)
            movie = session.get(Movie, movie_id)
            if movie:
                movie.omdb_status = OmdbStatus.ENRICHED
                omdb = OmdbData(movie_id=movie.id, title=movie.title)
                session.add(omdb)
                session.flush()
            return omdb

        def fake_enrich_show(session, show_id, force=False):
            show_ids_processed.append(show_id)
            show = session.get(Show, show_id)
            if show:
                show.omdb_status = OmdbStatus.ENRICHED
                omdb = OmdbData(show_id=show.id, title=show.title)
                session.add(omdb)
                session.flush()
            return omdb

        with (
            patch("file_fetcher.services.enrichment.enrich_single", side_effect=fake_enrich_movie),
            patch("file_fetcher.services.enrichment.enrich_single_show", side_effect=fake_enrich_show),
        ):
            from file_fetcher.services.enrichment import run_enrichment_batch

            stats = run_enrichment_batch(db_session, batch_limit=10, daily_quota=900)

        assert m.id in movie_ids_processed
        assert s.id in show_ids_processed
        assert stats["movies_enriched"] == 1
        assert stats["shows_enriched"] == 1

    def test_show_skip_already_enriched(self, db_session, show):
        """Show with status=enriched is skipped (force=False)."""
        show.omdb_status = OmdbStatus.ENRICHED
        omdb = OmdbData(show_id=show.id, title="Breaking Bad")
        db_session.add(omdb)
        db_session.flush()

        with patch("file_fetcher.services.enrichment.requests.get") as mock_get:
            from file_fetcher.services.enrichment import enrich_single_show

            result = enrich_single_show(db_session, show.id, force=False)

        mock_get.assert_not_called()
        assert result is not None


# ---------------------------------------------------------------------------
# Story 2.4: not-found catalog service
# ---------------------------------------------------------------------------


class TestGetNotFound:
    """Tests for catalog.get_not_found() — Story 2.4/2.5."""

    def test_get_not_found_movies_and_shows(self, db_session):
        """Returns both movies and shows with omdb_status=not_found."""
        m1 = Movie(title="Ghost Film", year=2010)
        m2 = Movie(title="Normal Film", year=2011)
        s1 = Show(title="Ghost Show", year=2012)
        db_session.add_all([m1, m2, s1])
        db_session.flush()
        m1.omdb_status = OmdbStatus.NOT_FOUND
        s1.omdb_status = OmdbStatus.NOT_FOUND
        db_session.flush()

        from file_fetcher.services.catalog import get_not_found

        entries = get_not_found(db_session)
        titles = {e.title for e in entries}
        assert "Ghost Film" in titles
        assert "Ghost Show" in titles
        assert "Normal Film" not in titles

    def test_get_not_found_empty(self, db_session):
        """Returns empty list when no not_found entries."""
        from file_fetcher.services.catalog import get_not_found

        entries = get_not_found(db_session)
        assert entries == []

    def test_get_not_found_includes_remote_paths(self, db_session):
        """Remote paths are included per entry."""
        from file_fetcher.models.enums import MediaType
        from file_fetcher.models.remote_file import RemoteFile

        m = Movie(title="Lost Film", year=2005)
        db_session.add(m)
        db_session.flush()
        m.omdb_status = OmdbStatus.NOT_FOUND

        rf = RemoteFile(
            movie_id=m.id,
            remote_path="/media/films/lost.mkv",
            filename="lost.mkv",
            media_type=MediaType.film,
        )
        db_session.add(rf)
        db_session.flush()

        from file_fetcher.services.catalog import get_not_found

        entries = get_not_found(db_session)
        assert len(entries) == 1
        assert "/media/films/lost.mkv" in entries[0].remote_paths
