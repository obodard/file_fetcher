"""Tests for PATCH /api/catalog/{id}/override and POST /api/catalog/{id}/enrich — Story 10.3."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from file_fetcher.schemas.catalog import TitleDetail


def _make_detail(
    id: int = 1,
    title: str = "Test Movie",
    year: int = 2020,
    override_title: str | None = None,
    override_omdb_id: str | None = None,
) -> TitleDetail:
    return TitleDetail(
        id=id,
        title=title,
        year=year,
        media_type="film",
        omdb_status="enriched",
        availability="remote_only",
        remote_paths=["/remote/test.mkv"],
        local_paths=[],
        override_title=override_title,
        override_omdb_id=override_omdb_id,
    )


@pytest.fixture
def app():
    from file_fetcher.web.app import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestOverridePatch:
    def test_override_returns_200_with_partial(self, client):
        """PATCH /api/catalog/1/override → 200 with HTML partial."""
        entry = _make_detail(override_title="New Title")
        with (
            patch("file_fetcher.web.routes.api.set_override", return_value=True),
            patch("file_fetcher.web.routes.api.get_by_id", return_value=entry),
        ):
            resp = client.patch(
                "/api/catalog/1/override",
                data={"override_title": "New Title", "omdb_id": ""},
            )
        assert resp.status_code == 200
        assert "override-section-1" in resp.text

    def test_override_returns_404_when_not_found(self, client):
        """PATCH /api/catalog/9999/override → 404 when entry not found."""
        with patch("file_fetcher.web.routes.api.set_override", return_value=False):
            resp = client.patch(
                "/api/catalog/9999/override",
                data={"override_title": "Title", "omdb_id": ""},
            )
        assert resp.status_code == 404

    def test_override_includes_toast(self, client):
        """PATCH response body includes a success toast fragment."""
        entry = _make_detail()
        with (
            patch("file_fetcher.web.routes.api.set_override", return_value=True),
            patch("file_fetcher.web.routes.api.get_by_id", return_value=entry),
        ):
            resp = client.patch(
                "/api/catalog/1/override",
                data={"override_title": "Title", "omdb_id": ""},
            )
        assert "Override saved" in resp.text

    def test_override_calls_set_override(self, client):
        """PATCH calls set_override with correct arguments."""
        entry = _make_detail()
        with (
            patch("file_fetcher.web.routes.api.set_override", return_value=True) as mock_so,
            patch("file_fetcher.web.routes.api.get_by_id", return_value=entry),
        ):
            client.patch(
                "/api/catalog/1/override",
                data={"override_title": "Better Title", "omdb_id": "tt1234567"},
            )
        mock_so.assert_called_once()
        args = mock_so.call_args
        assert args[0][1] == 1  # catalog_id
        assert args[0][2] == "Better Title"
        assert args[0][3] == "tt1234567"


class TestEnrichPost:
    def test_enrich_success_returns_200(self, client):
        """POST /api/catalog/1/enrich → 200 on success."""
        entry = _make_detail()
        with (
            patch("file_fetcher.web.routes.api.enrich_one", return_value=(True, "Test Movie (2020)")),
            patch("file_fetcher.web.routes.api.get_by_id", return_value=entry),
        ):
            resp = client.post("/api/catalog/1/enrich")
        assert resp.status_code == 200

    def test_enrich_success_toast_shows_title(self, client):
        """POST /api/catalog/1/enrich success toast contains enriched title."""
        entry = _make_detail()
        with (
            patch("file_fetcher.web.routes.api.enrich_one", return_value=(True, "Test Movie (2020)")),
            patch("file_fetcher.web.routes.api.get_by_id", return_value=entry),
        ):
            resp = client.post("/api/catalog/1/enrich")
        assert "Test Movie" in resp.text

    def test_enrich_failure_returns_200_with_error_toast(self, client):
        """POST /api/catalog/1/enrich failure → 200 with error toast."""
        entry = _make_detail()
        with (
            patch("file_fetcher.web.routes.api.enrich_one", return_value=(False, "not_found")),
            patch("file_fetcher.web.routes.api.get_by_id", return_value=entry),
        ):
            resp = client.post("/api/catalog/1/enrich")
        assert resp.status_code == 200
        assert "alert-error" in resp.text

    def test_enrich_returns_partial_with_id(self, client):
        """POST /api/catalog/1/enrich response includes override section HTML."""
        entry = _make_detail(id=1)
        with (
            patch("file_fetcher.web.routes.api.enrich_one", return_value=(True, "Test Movie (2020)")),
            patch("file_fetcher.web.routes.api.get_by_id", return_value=entry),
        ):
            resp = client.post("/api/catalog/1/enrich")
        assert "override-section-1" in resp.text

    def test_enrich_not_found_catalog_returns_404(self, client):
        """POST /api/catalog/9999/enrich → 404 when catalog entry gone."""
        with (
            patch("file_fetcher.web.routes.api.enrich_one", return_value=(False, "Entry not found")),
            patch("file_fetcher.web.routes.api.get_by_id", return_value=None),
        ):
            resp = client.post("/api/catalog/9999/enrich")
        assert resp.status_code == 404


class TestNotFoundOnSettingsPage:
    def test_not_found_section_appears_when_entries(self, client):
        """Settings page shows Not Found section when there are unmatched entries."""
        from file_fetcher.services.catalog import NotFoundEntry

        nf = NotFoundEntry(
            id=5,
            media_kind="movie",
            title="Missing Film",
            year=2019,
            remote_paths=["/remote/missing.mkv"],
        )

        mock_settings = []
        with (
            patch("file_fetcher.web.routes.settings.settings_service.get_all", return_value=mock_settings),
            patch("file_fetcher.web.routes.settings.get_not_found", return_value=[nf]),
        ):
            resp = client.get("/settings")

        assert resp.status_code == 200
        assert "Missing Film" in resp.text
        assert "/title/5?edit=1" in resp.text

    def test_not_found_section_hidden_when_empty(self, client):
        """Settings page hides Not Found section when all entries are matched."""
        with (
            patch("file_fetcher.web.routes.settings.settings_service.get_all", return_value=[]),
            patch("file_fetcher.web.routes.settings.get_not_found", return_value=[]),
        ):
            resp = client.get("/settings")

        assert resp.status_code == 200
        assert "Not Found" not in resp.text or "not_found_entries" not in resp.text


class TestSetOverrideUnit:
    def test_set_override_movie(self):
        """set_override updates title_override and override_omdb_id on Movie."""
        from unittest.mock import MagicMock
        from file_fetcher.services.catalog import set_override
        from file_fetcher.models.movie import Movie

        session = MagicMock()
        movie = MagicMock(spec=Movie)

        def _get(model, pk):
            if model is Movie:
                return movie
            return None

        session.get.side_effect = _get

        result = set_override(session, 1, "Better Title", "tt9999999")
        assert result is True
        assert movie.title_override == "Better Title"
        assert movie.override_omdb_id == "tt9999999"

    def test_set_override_clears_with_empty(self):
        """set_override clears title_override when empty string passed."""
        from unittest.mock import MagicMock
        from file_fetcher.services.catalog import set_override
        from file_fetcher.models.movie import Movie

        session = MagicMock()
        movie = MagicMock(spec=Movie)

        def _get(model, pk):
            if model is Movie:
                return movie
            return None

        session.get.side_effect = _get

        result = set_override(session, 1, "", None)
        assert result is True
        assert movie.title_override is None
        assert movie.override_omdb_id is None
