"""Tests for POST /api/queue/add and POST /api/queue/download-now — Story 8.2."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from file_fetcher.schemas.catalog import TitleDetail
from file_fetcher.services.queue_service import AlreadyQueuedError


def _make_detail(id: int = 1, availability: str = "remote_only") -> TitleDetail:
    return TitleDetail(
        id=id,
        title="Test Movie",
        year=2024,
        media_type="film",
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
    return TestClient(app, raise_server_exceptions=False)


class TestQueueAddEndpoint:
    def test_returns_200_on_success(self, client):
        """POST /api/queue/add → 200 with updated action buttons HTML."""
        detail = _make_detail(availability="remote_only_downloading")
        with (
            patch("file_fetcher.web.routes.api.enqueue_catalog_entry"),
            patch("file_fetcher.web.routes.api.get_by_id", return_value=detail),
        ):
            response = client.post("/api/queue/add", data={"catalog_id": "1"})
        assert response.status_code == 200

    def test_response_is_html(self, client):
        """POST /api/queue/add response content-type is HTML."""
        detail = _make_detail(availability="remote_only_downloading")
        with (
            patch("file_fetcher.web.routes.api.enqueue_catalog_entry"),
            patch("file_fetcher.web.routes.api.get_by_id", return_value=detail),
        ):
            response = client.post("/api/queue/add", data={"catalog_id": "1"})
        assert "text/html" in response.headers.get("content-type", "")

    def test_success_response_contains_toast(self, client):
        """Success response includes a toast OOB HTML fragment."""
        detail = _make_detail(availability="remote_only_downloading")
        with (
            patch("file_fetcher.web.routes.api.enqueue_catalog_entry"),
            patch("file_fetcher.web.routes.api.get_by_id", return_value=detail),
        ):
            response = client.post("/api/queue/add", data={"catalog_id": "1"})
        assert "toast-container" in response.text
        assert "Added to queue" in response.text

    def test_duplicate_returns_409(self, client):
        """POST /api/queue/add with already-queued entry → 409."""
        with patch(
            "file_fetcher.web.routes.api.enqueue_catalog_entry",
            side_effect=AlreadyQueuedError("already queued"),
        ):
            response = client.post("/api/queue/add", data={"catalog_id": "1"})
        assert response.status_code == 409

    def test_duplicate_response_contains_error_toast(self, client):
        """409 response includes an error toast fragment."""
        with patch(
            "file_fetcher.web.routes.api.enqueue_catalog_entry",
            side_effect=AlreadyQueuedError("already queued"),
        ):
            response = client.post("/api/queue/add", data={"catalog_id": "1"})
        assert "alert-error" in response.text
        assert "Already in queue" in response.text


class TestQueueDownloadNowEndpoint:
    def test_returns_200_on_success(self, client):
        """POST /api/queue/download-now → 200 on success."""
        detail = _make_detail(availability="remote_only_downloading")
        with (
            patch("file_fetcher.web.routes.api.enqueue_catalog_entry"),
            patch("file_fetcher.web.routes.api.get_by_id", return_value=detail),
        ):
            response = client.post("/api/queue/download-now", data={"catalog_id": "1"})
        assert response.status_code == 200

    def test_enqueue_called_with_priority_999(self, client):
        """download-now endpoint passes priority=999."""
        detail = _make_detail(availability="remote_only_downloading")
        with (
            patch("file_fetcher.web.routes.api.enqueue_catalog_entry") as mock_enqueue,
            patch("file_fetcher.web.routes.api.get_by_id", return_value=detail),
        ):
            client.post("/api/queue/download-now", data={"catalog_id": "7"})
        mock_enqueue.assert_called_once()
        call_kwargs = mock_enqueue.call_args
        # priority=999 can be positional or keyword
        args = call_kwargs.args
        kwargs = call_kwargs.kwargs
        priority_passed = kwargs.get("priority") or (args[2] if len(args) > 2 else None)
        assert priority_passed == 999

    def test_duplicate_returns_409(self, client):
        """POST /api/queue/download-now with already-queued entry → 409."""
        with patch(
            "file_fetcher.web.routes.api.enqueue_catalog_entry",
            side_effect=AlreadyQueuedError("already queued"),
        ):
            response = client.post("/api/queue/download-now", data={"catalog_id": "1"})
        assert response.status_code == 409


class TestAlreadyQueuedError:
    def test_is_value_error_subclass(self):
        """AlreadyQueuedError should be a ValueError subclass."""
        err = AlreadyQueuedError("msg")
        assert isinstance(err, ValueError)

    def test_message_stored(self):
        """AlreadyQueuedError stores the message."""
        err = AlreadyQueuedError("test message")
        assert "test message" in str(err)
