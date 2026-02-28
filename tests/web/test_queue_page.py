"""Tests for GET /queue page and per-item queue action endpoints — Story 9.1."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from file_fetcher.web.routes.queue import QueueRow


def _make_row(
    id: int = 1,
    title: str = "Test Movie",
    catalog_id: int = 10,
    status: str = "pending",
    priority: int = 0,
    progress: int = 0,
    error_message: str | None = None,
) -> QueueRow:
    return QueueRow(
        id=id,
        title=title,
        catalog_id=catalog_id,
        status=status,
        priority=priority,
        progress=progress,
        error_message=error_message,
    )


@pytest.fixture
def app():
    from file_fetcher.web.app import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


class TestQueuePage:
    def test_get_queue_returns_200(self, client):
        """GET /queue → 200."""
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=[]):
            response = client.get("/queue")
        assert response.status_code == 200

    def test_get_queue_is_html(self, client):
        """GET /queue response is HTML."""
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=[]):
            response = client.get("/queue")
        assert "text/html" in response.headers.get("content-type", "")

    def test_empty_state_shown_when_no_entries(self, client):
        """Shows empty state text when queue is empty."""
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=[]):
            response = client.get("/queue")
        assert "Your queue is empty" in response.text

    def test_empty_state_contains_catalogue_link(self, client):
        """Empty state includes a link back to the catalogue."""
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=[]):
            response = client.get("/queue")
        assert "Browse Catalogue" in response.text
        assert 'href="/"' in response.text

    def test_table_rows_rendered_for_entries(self, client):
        """Table rows are rendered for each queue entry."""
        rows = [_make_row(id=1, title="Inception"), _make_row(id=2, title="Dune")]
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=rows):
            response = client.get("/queue")
        assert "Inception" in response.text
        assert "Dune" in response.text

    def test_row_ids_present_in_html(self, client):
        """Each row has id=row-{id} for HTMX OOB targeting."""
        rows = [_make_row(id=42, title="Matrix")]
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=rows):
            response = client.get("/queue")
        assert 'id="row-42"' in response.text

    def test_title_linked_to_detail_page(self, client):
        """Title is linked to /title/{catalog_id}."""
        rows = [_make_row(id=1, title="Gladiator", catalog_id=7)]
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=rows):
            response = client.get("/queue")
        assert "/title/7" in response.text
        assert "Gladiator" in response.text

    def test_status_badge_present(self, client):
        """Status badge rendered for each entry."""
        rows = [_make_row(id=1, status="pending")]
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=rows):
            response = client.get("/queue")
        assert "pending" in response.text

    def test_downloading_status_shows_progress_bar(self, client):
        """Progress bar shown for 'downloading' status."""
        rows = [_make_row(id=1, status="downloading", progress=42)]
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=rows):
            response = client.get("/queue")
        assert 'class="progress' in response.text
        assert "42" in response.text

    def test_retry_button_shown_for_failed(self, client):
        """Retry button rendered for failed entries."""
        rows = [_make_row(id=1, status="failed")]
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=rows):
            response = client.get("/queue")
        assert "Retry" in response.text

    def test_retry_button_not_shown_for_pending(self, client):
        """Retry button not rendered for pending entries."""
        rows = [_make_row(id=1, status="pending")]
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=rows):
            response = client.get("/queue")
        assert "Retry" not in response.text

    def test_remove_button_present(self, client):
        """Remove button rendered for each entry."""
        rows = [_make_row(id=1)]
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=rows):
            response = client.get("/queue")
        assert "Remove" in response.text

    def test_polling_attrs_present_on_tbody(self, client):
        """tbody#queue-rows has HTMX polling attributes."""
        rows = [_make_row(id=1)]
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=rows):
            response = client.get("/queue")
        assert 'id="queue-rows"' in response.text
        assert 'hx-get="/api/queue/rows"' in response.text
        assert "hx-trigger" in response.text

    def test_remove_modal_present(self, client):
        """Remove confirm modal is present in the page."""
        with patch("file_fetcher.web.routes.queue._fetch_queue_rows", return_value=[]):
            response = client.get("/queue")
        assert 'id="remove-modal"' in response.text


class TestQueueDeleteEndpoint:
    def test_delete_returns_200(self, client):
        """DELETE /api/queue/{id} → 200 on success."""
        with patch("file_fetcher.web.routes.api.remove_from_queue"):
            response = client.delete("/api/queue/1")
        assert response.status_code == 200

    def test_delete_not_found_returns_404(self, client):
        """DELETE /api/queue/{id} → 404 when entry not found."""
        with patch(
            "file_fetcher.web.routes.api.remove_from_queue",
            side_effect=ValueError("not found"),
        ):
            response = client.delete("/api/queue/999")
        assert response.status_code == 404

    def test_delete_returns_oob_delete_fragment(self, client):
        """DELETE response includes OOB fragment to remove the row."""
        with patch("file_fetcher.web.routes.api.remove_from_queue"):
            response = client.delete("/api/queue/5")
        assert "row-5" in response.text
        assert "hx-swap-oob" in response.text

    def test_delete_returns_toast(self, client):
        """DELETE response includes toast notification."""
        with patch("file_fetcher.web.routes.api.remove_from_queue"):
            response = client.delete("/api/queue/1")
        assert "Removed from queue" in response.text


class TestQueueRetryEndpoint:
    def test_retry_returns_200(self, client):
        """POST /api/queue/{id}/retry → 200 on success."""
        with (
            patch("file_fetcher.web.routes.api.retry_entry"),
            patch("file_fetcher.web.routes.api._render_queue_row_partial", return_value="<tr id='row-1'></tr>"),
        ):
            response = client.post("/api/queue/1/retry")
        assert response.status_code == 200

    def test_retry_not_found_returns_404(self, client):
        """POST /api/queue/{id}/retry → 404 when entry not found."""
        with patch(
            "file_fetcher.web.routes.api.retry_entry",
            side_effect=ValueError("not found"),
        ):
            response = client.post("/api/queue/999/retry")
        assert response.status_code == 404

    def test_retry_response_contains_toast(self, client):
        """Retry success response includes a toast."""
        with (
            patch("file_fetcher.web.routes.api.retry_entry"),
            patch("file_fetcher.web.routes.api._render_queue_row_partial", return_value="<tr id='row-1'></tr>"),
        ):
            response = client.post("/api/queue/1/retry")
        assert "Retry" in response.text


class TestQueuePriorityEndpoint:
    def _mock_entry(self, queue_id: int = 1, priority: int = 5):
        """Patch get_session to return a mock entry."""
        from unittest.mock import MagicMock

        entry = MagicMock()
        entry.id = queue_id
        entry.priority = priority

        mock_session = MagicMock()
        mock_session.get.return_value = entry
        mock_session.__enter__ = lambda s: mock_session
        mock_session.__exit__ = MagicMock(return_value=False)
        return mock_session, entry

    def test_patch_returns_200(self, client):
        """PATCH /api/queue/{id}/priority → 200 on success."""
        mock_session, entry = self._mock_entry()
        with (
            patch("file_fetcher.web.routes.api.get_session", return_value=mock_session),
            patch("file_fetcher.web.routes.api._render_queue_row_partial", return_value="<tr id='row-1'></tr>"),
        ):
            response = client.patch("/api/queue/1/priority", data={"delta": "1"})
        assert response.status_code == 200

    def test_patch_not_found_returns_404(self, client):
        """PATCH /api/queue/{id}/priority → 404 when entry not found."""
        mock_session = patch("file_fetcher.web.routes.api.get_session")
        from unittest.mock import MagicMock

        ms = MagicMock()
        ms.get.return_value = None
        ms.__enter__ = lambda s: ms
        ms.__exit__ = MagicMock(return_value=False)

        with (
            patch("file_fetcher.web.routes.api.get_session", return_value=ms),
            patch("file_fetcher.web.routes.api._render_queue_row_partial", return_value=""),
        ):
            response = client.patch("/api/queue/999/priority", data={"delta": "1"})
        assert response.status_code == 404
