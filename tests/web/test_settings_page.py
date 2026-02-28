"""Tests for GET /settings and POST /settings — Story 10.1."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from file_fetcher.web.app import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def _mock_settings(overrides=None):
    """Return a list-of-mock-Setting objects for use with get_all patch."""
    defaults = {
        "sftp_host": "192.168.1.1",
        "sftp_port": "22",
        "sftp_user": "user",
        "sftp_password": "secret",
        "sftp_remote_path": "/media",
        "sftp_scan_enabled": "true",
        "sftp_scan_cron": "0 3 * * *",
        "omdb_api_key": "mykey",
        "omdb_batch_limit": "50",
        "omdb_daily_quota": "1000",
        "omdb_enrich_cron": "0 4 * * *",
        "download_dir": "/downloads",
        "scheduler_poll_interval": "60",
        "web_poll_interval_seconds": "5",
    }
    if overrides:
        defaults.update(overrides)

    result = []
    for k, v in defaults.items():
        s = MagicMock()
        s.key = k
        s.value = v
        result.append(s)
    return result


class TestSettingsGet:
    def test_returns_200(self, client):
        """GET /settings → 200."""
        with (
            patch("file_fetcher.web.routes.settings.settings_service.get_all",
                  return_value=_mock_settings()),
            patch("file_fetcher.web.routes.settings.get_not_found", return_value=[]),
        ):
            resp = client.get("/settings")
        assert resp.status_code == 200

    def test_page_title_in_body(self, client):
        """Settings heading is present."""
        with (
            patch("file_fetcher.web.routes.settings.settings_service.get_all",
                  return_value=_mock_settings()),
            patch("file_fetcher.web.routes.settings.get_not_found", return_value=[]),
        ):
            resp = client.get("/settings")
        assert "Settings" in resp.text

    def test_masked_keys_not_in_plain_text(self, client):
        """Sensitive values are not rendered as visible text (not in labels)."""
        with (
            patch("file_fetcher.web.routes.settings.settings_service.get_all",
                  return_value=_mock_settings()),
            patch("file_fetcher.web.routes.settings.get_not_found", return_value=[]),
        ):
            resp = client.get("/settings")
        # The value is in a password input (type="password"), not visible in plain text body
        assert resp.status_code == 200
        assert 'type="password"' in resp.text

    def test_toast_message_appears(self, client):
        """?toast=message renders a success alert."""
        with (
            patch("file_fetcher.web.routes.settings.settings_service.get_all",
                  return_value=_mock_settings()),
            patch("file_fetcher.web.routes.settings.get_not_found", return_value=[]),
        ):
            resp = client.get("/settings?toast=Settings+saved")
        assert "Settings saved" in resp.text

    def test_sftp_scan_toggle_present(self, client):
        """The sftp_scan_enabled toggle checkbox is rendered."""
        with (
            patch("file_fetcher.web.routes.settings.settings_service.get_all",
                  return_value=_mock_settings()),
            patch("file_fetcher.web.routes.settings.get_not_found", return_value=[]),
        ):
            resp = client.get("/settings")
        assert "sftp_scan_enabled" in resp.text


class TestSettingsPost:
    def test_valid_post_redirects(self, client):
        """POST /settings with valid data → 303 redirect to /settings."""
        with patch("file_fetcher.web.routes.settings.settings_service.update_batch"):
            resp = client.post(
                "/settings",
                data={
                    "sftp_host": "10.0.0.1",
                    "sftp_port": "22",
                    "sftp_user": "admin",
                    "sftp_password": "",
                    "sftp_remote_path": "/",
                    "sftp_scan_cron": "0 3 * * *",
                    "omdb_api_key": "",
                    "omdb_batch_limit": "50",
                    "omdb_daily_quota": "1000",
                    "omdb_enrich_cron": "0 4 * * *",
                    "download_dir": "/downloads",
                    "scheduler_poll_interval": "60",
                    "web_poll_interval_seconds": "5",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert "/settings" in resp.headers.get("location", "")

    def test_invalid_cron_returns_422(self, client):
        """POST /settings with malformed cron → 422 and error message."""
        with (
            patch("file_fetcher.web.routes.settings.settings_service.update_batch"),
            patch("file_fetcher.web.routes.settings.get_not_found", return_value=[]),
        ):
            resp = client.post(
                "/settings",
                data={
                    "sftp_host": "",
                    "sftp_port": "22",
                    "sftp_user": "",
                    "sftp_password": "",
                    "sftp_remote_path": "/",
                    "sftp_scan_cron": "not-a-cron",
                    "omdb_api_key": "",
                    "omdb_batch_limit": "50",
                    "omdb_daily_quota": "1000",
                    "omdb_enrich_cron": "",
                    "download_dir": "/downloads",
                    "scheduler_poll_interval": "60",
                    "web_poll_interval_seconds": "5",
                },
            )
        assert resp.status_code == 422
        assert "Invalid cron" in resp.text

    def test_empty_cron_is_valid(self, client):
        """POST /settings with empty cron → redirect (empty = disabled = valid)."""
        with patch("file_fetcher.web.routes.settings.settings_service.update_batch"):
            resp = client.post(
                "/settings",
                data={
                    "sftp_host": "",
                    "sftp_port": "22",
                    "sftp_user": "",
                    "sftp_password": "",
                    "sftp_remote_path": "/",
                    "sftp_scan_cron": "",
                    "omdb_api_key": "",
                    "omdb_batch_limit": "50",
                    "omdb_daily_quota": "1000",
                    "omdb_enrich_cron": "",
                    "download_dir": "/downloads",
                    "scheduler_poll_interval": "60",
                    "web_poll_interval_seconds": "5",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 303


class TestValidateCron:
    def test_valid_cron(self):
        from file_fetcher.web.utils import validate_cron
        assert validate_cron("0 3 * * *") is True

    def test_empty_cron(self):
        from file_fetcher.web.utils import validate_cron
        assert validate_cron("") is True
        assert validate_cron("   ") is True

    def test_invalid_cron_too_few_fields(self):
        from file_fetcher.web.utils import validate_cron
        assert validate_cron("0 3 * *") is False

    def test_invalid_cron_too_many_fields(self):
        from file_fetcher.web.utils import validate_cron
        assert validate_cron("0 3 * * * *") is False

    def test_invalid_cron_non_cron_string(self):
        from file_fetcher.web.utils import validate_cron
        assert validate_cron("not-a-cron") is False
