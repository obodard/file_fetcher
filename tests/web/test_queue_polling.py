"""Tests for HTMX polling endpoints — Story 9.2."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from file_fetcher.web.routes.queue import QueueRow


def _make_row(
    id: int = 1,
    title: str = "Test Movie",
    status: str = "pending",
    **kwargs,
) -> QueueRow:
    return QueueRow(
        id=id,
        title=title,
        catalog_id=kwargs.get("catalog_id", id + 9),
        status=status,
        priority=kwargs.get("priority", 0),
        progress=kwargs.get("progress", 0),
        error_message=kwargs.get("error_message"),
    )


@pytest.fixture
def app():
    from file_fetcher.web.app import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestQueueRowsFragment:
    def test_get_rows_returns_200(self, client):
        """GET /api/queue/rows → 200."""
        with patch(
            "file_fetcher.web.routes.queue._fetch_queue_rows",
            return_value=[],
        ):
            response = client.get("/api/queue/rows")
        assert response.status_code == 200

    def test_get_rows_is_html(self, client):
        """GET /api/queue/rows response is HTML."""
        with patch(
            "file_fetcher.web.routes.queue._fetch_queue_rows",
            return_value=[],
        ):
            response = client.get("/api/queue/rows")
        assert "text/html" in response.headers.get("content-type", "")

    def test_get_rows_no_full_html_document(self, client):
        """GET /api/queue/rows must NOT return a full <html> page — fragment only."""
        rows = [_make_row(id=1, title="Blade Runner")]
        with patch(
            "file_fetcher.web.routes.queue._fetch_queue_rows",
            return_value=rows,
        ):
            response = client.get("/api/queue/rows")
        assert "<html" not in response.text.lower()

    def test_get_rows_contains_entry_title(self, client):
        """GET /api/queue/rows renders row titles."""
        rows = [_make_row(id=1, title="Mad Max"), _make_row(id=2, title="Interstellar")]
        with patch(
            "file_fetcher.web.routes.queue._fetch_queue_rows",
            return_value=rows,
        ):
            response = client.get("/api/queue/rows")
        assert "Mad Max" in response.text
        assert "Interstellar" in response.text

    def test_get_rows_empty_returns_200(self, client):
        """GET /api/queue/rows returns 200 even when queue is empty."""
        with patch(
            "file_fetcher.web.routes.queue._fetch_queue_rows",
            return_value=[],
        ):
            response = client.get("/api/queue/rows")
        assert response.status_code == 200

    def test_get_rows_contains_tr_elements(self, client):
        """GET /api/queue/rows contains <tr> elements for each row."""
        rows = [_make_row(id=5)]
        with patch(
            "file_fetcher.web.routes.queue._fetch_queue_rows",
            return_value=rows,
        ):
            response = client.get("/api/queue/rows")
        assert '<tr id="row-5"' in response.text


class TestQueueBadgeEndpoint:
    def _mock_session_with_count(self, count: int):
        """Return a mock get_session context manager yielding a session with count query."""
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.count.return_value = count

        ms = MagicMock()
        ms.query.return_value = mock_q
        ms.__enter__ = lambda s: ms
        ms.__exit__ = MagicMock(return_value=False)
        return ms

    def test_badge_returns_200(self, client):
        """GET /api/queue/badge → 200."""
        ms = self._mock_session_with_count(3)
        with patch("file_fetcher.web.routes.api.get_session", return_value=ms):
            response = client.get("/api/queue/badge")
        assert response.status_code == 200

    def test_badge_returns_count_as_string(self, client):
        """GET /api/queue/badge returns plain-text count when items present."""
        ms = self._mock_session_with_count(3)
        with patch("file_fetcher.web.routes.api.get_session", return_value=ms):
            response = client.get("/api/queue/badge")
        assert response.text == "3"

    def test_badge_returns_empty_string_when_zero(self, client):
        """GET /api/queue/badge returns empty string when no active items."""
        ms = self._mock_session_with_count(0)
        with patch("file_fetcher.web.routes.api.get_session", return_value=ms):
            response = client.get("/api/queue/badge")
        assert response.text == ""

    def test_badge_content_type_is_plain_text(self, client):
        """GET /api/queue/badge returns plain text content-type."""
        ms = self._mock_session_with_count(1)
        with patch("file_fetcher.web.routes.api.get_session", return_value=ms):
            response = client.get("/api/queue/badge")
        assert "text/plain" in response.headers.get("content-type", "")


class TestNavbarBadgePolling:
    def test_queue_page_has_badge_polling_in_navbar(self, client):
        """Navbar badge span has HTMX polling attributes."""
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=[]):
            response = client.get("/queue")
        assert 'id="queue-badge"' in response.text
        assert 'hx-get="/api/queue/badge"' in response.text

    def test_queue_page_badge_has_empty_hidden_class(self, client):
        """Navbar badge has empty:hidden CSS class."""
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=[]):
            response = client.get("/queue")
        assert "empty:hidden" in response.text


class TestPollIntervalConfiguration:
    def test_queue_page_embeds_poll_interval(self, client):
        """Queue page template uses poll_interval from app state."""
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=[]):
            response = client.get("/queue")
        # The default poll interval (5) should appear in the hx-trigger
        assert "hx-trigger" in response.text
        # Interval in seconds format
        assert "every" in response.text
