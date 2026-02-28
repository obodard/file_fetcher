"""Tests for catalog grid page and poster API — Story 7.2."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from file_fetcher.schemas.catalog import CatalogResult


def _make_entry(
    id: int = 1,
    title: str = "Test Movie",
    year: int = 2024,
    media_type: str = "film",
    availability: str = "remote_only",
) -> CatalogResult:
    return CatalogResult(
        id=id,
        title=title,
        year=year,
        media_type=media_type,
        omdb_status="found",
        availability=availability,
        remote_paths=["/remote/test.mkv"],
        local_paths=[],
    )


@pytest.fixture
def app():
    from file_fetcher.web.app import create_app

    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


class TestCatalogGrid:
    def test_get_index_returns_200(self, client):
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]):
            response = client.get("/")
        assert response.status_code == 200

    def test_contains_tablist(self, client):
        """Response must include role='tablist' for Films/Series tabs."""
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]):
            response = client.get("/")
        assert 'role="tablist"' in response.text

    def test_films_tab_present(self, client):
        """Response must include a Films tab link with type=movie param."""
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]):
            response = client.get("/")
        assert "type=movie" in response.text
        assert "Films" in response.text

    def test_series_tab_present(self, client):
        """Response must include a Series tab link with type=series param."""
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]):
            response = client.get("/")
        assert "type=series" in response.text
        assert "Series" in response.text

    def test_empty_state_when_no_entries(self, client):
        """Shows EmptyState component when no catalog entries match."""
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]):
            response = client.get("/")
        assert "Nothing here yet" in response.text

    def test_poster_cards_rendered_when_entries_present(self, client):
        """Poster cards are rendered when catalog entries exist."""
        entries = [_make_entry(id=1, title="Inception")]
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=entries):
            response = client.get("/")
        assert "Inception" in response.text
        assert "/api/posters/1" in response.text

    def test_movie_filter_param_passed(self, client):
        """?type=movie maps to media_type='film' in search_catalog call."""
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]) as mock_search:
            client.get("/?type=movie")
        mock_search.assert_called_once()
        kwargs = mock_search.call_args.kwargs
        assert kwargs.get("media_type") == "film"

    def test_series_filter_param_passed(self, client):
        """?type=series maps to media_type='series' in search_catalog call."""
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=[]) as mock_search:
            client.get("/?type=series")
        mock_search.assert_called_once()
        kwargs = mock_search.call_args.kwargs
        assert kwargs.get("media_type") == "series"

    def test_local_entry_shows_green_badge(self, client):
        """An in-collection entry must show the green 'In Collection' badge."""
        entries = [_make_entry(availability="in_collection")]
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=entries):
            response = client.get("/")
        assert "In Collection" in response.text
        assert "badge-success" in response.text

    def test_queued_entry_shows_blue_badge(self, client):
        """A downloading entry must show the blue 'Downloading' badge."""
        entries = [_make_entry(availability="remote_only_downloading")]
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=entries):
            response = client.get("/")
        assert "Downloading" in response.text
        assert "badge-info" in response.text

    def test_remote_entry_shows_grey_badge(self, client):
        """A remote-only entry must show the grey 'Remote' badge."""
        entries = [_make_entry(availability="remote_only")]
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=entries):
            response = client.get("/")
        assert "Remote" in response.text
        assert "badge-ghost" in response.text

    def test_add_to_queue_button_shown_for_remote_entry(self, client):
        """Quick-add button appears for remote-only entries."""
        entries = [_make_entry(availability="remote_only")]
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=entries):
            response = client.get("/")
        assert "hx-post" in response.text
        assert "/api/queue/add" in response.text

    def test_no_add_button_for_local_entry(self, client):
        """Quick-add button is hidden for in-collection entries."""
        entries = [_make_entry(availability="in_collection")]
        with patch("file_fetcher.web.routes.catalog.search_catalog", return_value=entries):
            response = client.get("/")
        # Poster card for local entry should NOT have hx-post queue/add
        assert "/api/queue/add" not in response.text


class TestPosterApi:
    def test_returns_svg_placeholder_when_no_omdb(self, client):
        """Returns SVG placeholder when no OmdbData blob is stored."""
        with patch("file_fetcher.web.routes.api.get_session") as mock_ctx:
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = None
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            response = client.get("/api/posters/999")
        assert response.status_code == 200
        assert "image/svg+xml" in response.headers["content-type"]
        assert b"<svg" in response.content

    def test_returns_poster_bytes_when_blob_stored(self, client):
        """Returns poster bytes with correct content-type when blob exists."""
        fake_blob = b"\xff\xd8\xff\xe0fake_jpeg_data"
        fake_omdb = MagicMock()
        fake_omdb.poster_blob = fake_blob
        fake_omdb.poster_content_type = "image/jpeg"
        with patch("file_fetcher.web.routes.api.get_session") as mock_ctx:
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.first.return_value = fake_omdb
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            response = client.get("/api/posters/1")
        assert response.status_code == 200
        assert response.content == fake_blob
        assert "image/jpeg" in response.headers["content-type"]

