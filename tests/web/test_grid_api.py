"""Tests for GET /api/grid — HTMX infinite scroll fragment endpoint."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from file_fetcher.web.app import create_app

# ── Shared fixture ────────────────────────────────────────────────────────────

@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def _make_entry(title: str = "Test Movie", media_type: str = "film") -> MagicMock:
    e = MagicMock()
    e.id = 1
    e.title = title
    e.year = 2020
    e.media_type = media_type
    e.omdb_status = "enriched"
    e.availability = "in_collection"
    e.remote_paths = []
    e.local_paths = ["/some/path.mkv"]
    e.genre = "Action"
    e.director = "Jane Doe"
    e.actors = "Actor A, Actor B"
    e.imdb_rating = "7.5"
    e.poster_url = "/api/posters/1"
    return e


# ── Basic fragment response ───────────────────────────────────────────────────

class TestGridFragment:
    """GET /api/grid returns a partial HTML fragment (no <html> tag)."""

    def test_returns_200(self, client: TestClient) -> None:
        with patch(
            "file_fetcher.web.routes.api.search_catalog",
            return_value=[_make_entry()],
        ):
            resp = client.get("/api/grid?offset=0")
        assert resp.status_code == 200

    def test_response_is_fragment_not_full_page(self, client: TestClient) -> None:
        with patch(
            "file_fetcher.web.routes.api.search_catalog",
            return_value=[_make_entry()],
        ):
            resp = client.get("/api/grid?offset=0")
        assert "<html" not in resp.text.lower()
        assert "<!doctype" not in resp.text.lower()

    def test_response_contains_poster_card(self, client: TestClient) -> None:
        with patch(
            "file_fetcher.web.routes.api.search_catalog",
            return_value=[_make_entry("Inception")],
        ):
            resp = client.get("/api/grid?offset=0")
        assert "Inception" in resp.text

    def test_empty_response_when_offset_beyond_results(self, client: TestClient) -> None:
        """When search_catalog returns empty (offset past end), fragment is empty."""
        with patch(
            "file_fetcher.web.routes.api.search_catalog",
            return_value=[],
        ):
            resp = client.get("/api/grid?offset=100")
        assert resp.status_code == 200
        # No poster cards in output
        assert "poster" not in resp.text.lower() or resp.text.strip() == ""

    def test_type_filter_passed_through(self, client: TestClient) -> None:
        with patch(
            "file_fetcher.web.routes.api.search_catalog",
            return_value=[],
        ) as mock_search:
            client.get("/api/grid?type=movie")
        mock_search.assert_called_once()
        _, kwargs = mock_search.call_args
        assert kwargs.get("media_type") == "film"

    def test_series_type_filter(self, client: TestClient) -> None:
        with patch(
            "file_fetcher.web.routes.api.search_catalog",
            return_value=[],
        ) as mock_search:
            client.get("/api/grid?type=series")
        mock_search.assert_called_once()
        _, kwargs = mock_search.call_args
        assert kwargs.get("media_type") == "series"

    def test_sentinel_present_when_limit_entries_returned(self, client: TestClient) -> None:
        """Last card gets hx-trigger sentinel when entries==limit."""
        entries = [_make_entry(f"Movie {i}") for i in range(2)]
        with patch(
            "file_fetcher.web.routes.api.search_catalog",
            return_value=entries,
        ):
            resp = client.get("/api/grid?limit=2")
        # Sentinel has hx-trigger=revealed
        assert "revealed" in resp.text

    def test_no_sentinel_when_fewer_than_limit(self, client: TestClient) -> None:
        """Sentinel is NOT emitted when entries < limit (end of data)."""
        entries = [_make_entry("Solo Movie")]  # 1 entry, limit=2 default 40
        with patch(
            "file_fetcher.web.routes.api.search_catalog",
            return_value=entries,
        ):
            resp = client.get("/api/grid?limit=40")
        assert "revealed" not in resp.text


# ── Post-filters ──────────────────────────────────────────────────────────────

class TestGridFilters:

    def test_genre_filter_excludes_non_matching(self, client: TestClient) -> None:
        comedy = _make_entry("Comedy Film")
        comedy.genre = "Comedy"
        action = _make_entry("Action Film")
        action.genre = "Action"
        with patch(
            "file_fetcher.web.routes.api.search_catalog",
            return_value=[comedy, action],
        ):
            resp = client.get("/api/grid?genre=Action")
        assert "Action Film" in resp.text
        assert "Comedy Film" not in resp.text

    def test_availability_local_filter(self, client: TestClient) -> None:
        local = _make_entry("Local Film")
        local.availability = "in_collection"
        remote = _make_entry("Remote Film")
        remote.availability = "remote_only"
        with patch(
            "file_fetcher.web.routes.api.search_catalog",
            return_value=[local, remote],
        ):
            resp = client.get("/api/grid?availability=local")
        assert "Local Film" in resp.text
        assert "Remote Film" not in resp.text

    def test_year_min_filter(self, client: TestClient) -> None:
        old = _make_entry("Old Film")
        old.year = 1990
        new = _make_entry("New Film")
        new.year = 2023
        with patch(
            "file_fetcher.web.routes.api.search_catalog",
            return_value=[old, new],
        ):
            resp = client.get("/api/grid?year_min=2000")
        assert "New Film" in resp.text
        assert "Old Film" not in resp.text


# ── AI search path ────────────────────────────────────────────────────────────

class TestGridAI:

    def test_ai_flag_without_api_key_returns_warning(self, client: TestClient) -> None:
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("GOOGLE_API_KEY", None)
            os.environ.pop("GEMINI_API_KEY", None)
            resp = client.get("/api/grid?ai=1&q=sci-fi")
        assert resp.status_code == 200
        assert "alert" in resp.text.lower() or "not configured" in resp.text.lower()

    def test_ai_flag_triggers_agent_path(self, client: TestClient) -> None:
        agent_mock = MagicMock()
        ai_results = [{"title": "Blade Runner", "year": 1982, "media_type": "film"}]
        entry = _make_entry("Blade Runner")
        entry.title = "Blade Runner"

        with (
            patch.dict("os.environ", {"GOOGLE_API_KEY": "fake-key"}),
            patch(
                "file_fetcher.agent.agent.create_catalog_agent",
                return_value=agent_mock,
            ),
            patch(
                "file_fetcher.agent.agent.run_catalog_agent",
                return_value=ai_results,
            ),
            patch(
                "file_fetcher.web.routes.api.search_catalog",
                return_value=[entry],
            ),
        ):
            resp = client.get("/api/grid?ai=1&q=sci-fi")

        assert resp.status_code == 200
        # Should not be a full page
        assert "<html" not in resp.text.lower()
