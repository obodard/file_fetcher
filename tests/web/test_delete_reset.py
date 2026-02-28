"""Tests for DELETE /api/catalog/{id} and POST /api/catalog/reset — Story 10.2."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from file_fetcher.web.app import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestDeleteEntry:
    def test_delete_returns_200_with_redirect_header(self, client):
        """DELETE /api/catalog/1 → 200 with HX-Redirect header when found."""
        with patch(
            "file_fetcher.web.routes.api.delete_catalog_entry",
            return_value=True,
        ):
            resp = client.delete("/api/catalog/1")
        assert resp.status_code == 200
        assert "HX-Redirect" in resp.headers

    def test_delete_redirect_points_to_catalog_root(self, client):
        """HX-Redirect header points to catalog root."""
        with patch(
            "file_fetcher.web.routes.api.delete_catalog_entry",
            return_value=True,
        ):
            resp = client.delete("/api/catalog/1")
        assert "/" in resp.headers.get("HX-Redirect", resp.headers.get("hx-redirect", ""))

    def test_delete_returns_404_when_not_found(self, client):
        """DELETE /api/catalog/9999 → 404 when entry does not exist."""
        with patch(
            "file_fetcher.web.routes.api.delete_catalog_entry",
            return_value=False,
        ):
            resp = client.delete("/api/catalog/9999")
        assert resp.status_code == 404

    def test_delete_error_toast_in_404_body(self, client):
        """404 response body contains an error toast fragment."""
        with patch(
            "file_fetcher.web.routes.api.delete_catalog_entry",
            return_value=False,
        ):
            resp = client.delete("/api/catalog/9999")
        assert "not found" in resp.text.lower()


class TestCatalogReset:
    def test_reset_returns_200_with_redirect_header(self, client):
        """POST /api/catalog/reset → 200 with HX-Redirect to settings."""
        with patch("file_fetcher.web.routes.api.full_reset"):
            resp = client.post("/api/catalog/reset")
        assert resp.status_code == 200
        redirect = resp.headers.get("HX-Redirect") or resp.headers.get("hx-redirect", "")
        assert "/settings" in redirect

    def test_reset_calls_full_reset(self, client):
        """POST /api/catalog/reset calls full_reset service function."""
        with patch("file_fetcher.web.routes.api.full_reset") as mock_reset:
            client.post("/api/catalog/reset")
        assert mock_reset.called


class TestDeleteCatalogEntryUnit:
    def test_delete_movie_found(self):
        """delete_catalog_entry returns True when movie exists and deletes it."""
        from unittest.mock import MagicMock
        from file_fetcher.services.catalog import delete_catalog_entry
        from file_fetcher.models.movie import Movie

        session = MagicMock()
        movie = MagicMock(spec=Movie)
        movie.id = 1

        def _get(model, pk):
            if model is Movie:
                return movie
            return None

        session.get.side_effect = _get

        with patch("file_fetcher.services.catalog.delete_entry") as mock_del:
            result = delete_catalog_entry(session, 1)

        assert result is True
        mock_del.assert_called_once_with(session, movie_id=1)

    def test_delete_not_found_returns_false(self):
        """delete_catalog_entry returns False when neither movie nor show found."""
        from unittest.mock import MagicMock
        from file_fetcher.services.catalog import delete_catalog_entry

        session = MagicMock()
        session.get.return_value = None

        result = delete_catalog_entry(session, 999)
        assert result is False
