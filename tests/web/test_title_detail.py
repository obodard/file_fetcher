"""Tests for GET /title/{id} — Story 8.1."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from file_fetcher.schemas.catalog import TitleDetail


def _make_detail(
    id: int = 1,
    title: str = "Inception",
    year: int = 2010,
    media_type: str = "film",
    availability: str = "remote_only",
    plot: str = "A dream heist film.",
) -> TitleDetail:
    return TitleDetail(
        id=id,
        title=title,
        year=year,
        media_type=media_type,
        omdb_status="found",
        availability=availability,
        remote_paths=["/remote/inception.mkv"],
        local_paths=[],
        plot=plot,
        genre="Action, Sci-Fi",
        director="Christopher Nolan",
        actors="Leonardo DiCaprio, Joseph Gordon-Levitt",
        imdb_rating="8.8",
        imdb_votes="2,300,000",
        rated="PG-13",
        released="16 Jul 2010",
        runtime="148 min",
        language="English",
        country="USA",
    )


@pytest.fixture
def app():
    from file_fetcher.web.app import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestTitleDetailPage:
    def test_returns_200_for_known_id(self, client):
        """GET /title/1 returns 200 when entry exists."""
        detail = _make_detail(id=1, title="Inception")
        with patch("file_fetcher.web.routes.catalog.get_by_id", return_value=detail):
            response = client.get("/title/1")
        assert response.status_code == 200

    def test_title_in_body(self, client):
        """Entry title appears in the rendered page."""
        detail = _make_detail(id=1, title="Inception")
        with patch("file_fetcher.web.routes.catalog.get_by_id", return_value=detail):
            response = client.get("/title/1")
        assert "Inception" in response.text

    def test_returns_404_for_unknown_id(self, client):
        """GET /title/9999 → 404 when no entry found."""
        with patch("file_fetcher.web.routes.catalog.get_by_id", return_value=None):
            response = client.get("/title/9999")
        assert response.status_code == 404

    def test_404_page_rendered_as_html(self, client):
        """404 response is an HTML page, not a bare JSON error."""
        with patch("file_fetcher.web.routes.catalog.get_by_id", return_value=None):
            response = client.get("/title/9999")
        assert "text/html" in response.headers.get("content-type", "")
        assert "Title not found" in response.text

    def test_404_has_back_link(self, client):
        """404 page includes a link back to the catalogue root."""
        with patch("file_fetcher.web.routes.catalog.get_by_id", return_value=None):
            response = client.get("/title/9999")
        assert 'href="/"' in response.text

    def test_metadata_fields_in_html(self, client):
        """Key metadata fields appear in the rendered detail page."""
        detail = _make_detail()
        with patch("file_fetcher.web.routes.catalog.get_by_id", return_value=detail):
            response = client.get("/title/1")
        body = response.text
        assert "Christopher Nolan" in body
        assert "Leonardo DiCaprio" in body
        assert "8.8" in body
        assert "Action, Sci-Fi" in body

    def test_remote_path_in_monospace_code(self, client):
        """Remote path is rendered inside a <code> element."""
        detail = _make_detail()
        with patch("file_fetcher.web.routes.catalog.get_by_id", return_value=detail):
            response = client.get("/title/1")
        assert "<code" in response.text
        assert "/remote/inception.mkv" in response.text

    def test_poster_img_points_to_api(self, client):
        """Poster <img> src points to /api/posters/{id}."""
        detail = _make_detail(id=42)
        with patch("file_fetcher.web.routes.catalog.get_by_id", return_value=detail):
            response = client.get("/title/42")
        assert "/api/posters/42" in response.text

    def test_availability_badge_local(self, client):
        """In-collection entry shows 'In Collection' badge."""
        detail = _make_detail(availability="in_collection")
        with patch("file_fetcher.web.routes.catalog.get_by_id", return_value=detail):
            response = client.get("/title/1")
        assert "In Collection" in response.text

    def test_availability_badge_remote(self, client):
        """Remote-only entry shows 'Remote Only' badge."""
        detail = _make_detail(availability="remote_only")
        with patch("file_fetcher.web.routes.catalog.get_by_id", return_value=detail):
            response = client.get("/title/1")
        assert "Remote" in response.text

    def test_tv_only_seasons_field(self, client):
        """total_seasons field only appears for series entries."""
        detail = TitleDetail(
            id=5,
            title="Breaking Bad",
            year=2008,
            media_type="series",
            omdb_status="found",
            availability="remote_only",
            remote_paths=["/remote/bb.mkv"],
            local_paths=[],
            total_seasons=5,
        )
        with patch("file_fetcher.web.routes.catalog.get_by_id", return_value=detail):
            response = client.get("/title/5")
        assert "Seasons" in response.text
        assert "5" in response.text

    def test_action_buttons_present_for_remote_entry(self, client):
        """Action buttons div is present for remote-only entries."""
        detail = _make_detail(availability="remote_only")
        with patch("file_fetcher.web.routes.catalog.get_by_id", return_value=detail):
            response = client.get("/title/1")
        assert "action-buttons" in response.text
        assert "/api/queue/add" in response.text
