"""Unit tests for app_runner (Story 6.2).

All tests use mocks — no real scheduler threads or DB connections are started.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


# ── scheduled_scan() ─────────────────────────────────────────────────────────


class TestScheduledScan:
    def test_scan_runs_when_enabled(self) -> None:
        """scheduled_scan calls run_full_scan when sftp_scan_enabled == 'true'."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with (
            patch("file_fetcher.app_runner.get_session", return_value=mock_session),
            patch("file_fetcher.app_runner.settings_service") as mock_svc,
            patch("file_fetcher.app_runner.run_full_scan") as mock_scan,
        ):
            mock_svc.get.return_value = "true"

            from file_fetcher.app_runner import scheduled_scan

            scheduled_scan()

        mock_scan.assert_called_once_with(mock_session)

    def test_scan_skips_when_disabled(self, caplog) -> None:
        """scheduled_scan logs and skips when sftp_scan_enabled == 'false'."""
        import logging

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with (
            patch("file_fetcher.app_runner.get_session", return_value=mock_session),
            patch("file_fetcher.app_runner.settings_service") as mock_svc,
            patch("file_fetcher.app_runner.run_full_scan") as mock_scan,
            caplog.at_level(logging.INFO, logger="file_fetcher.app_runner"),
        ):
            mock_svc.get.return_value = "false"

            from file_fetcher.app_runner import scheduled_scan

            scheduled_scan()

        mock_scan.assert_not_called()
        assert "SFTP scan disabled" in caplog.text

    def test_scan_logs_error_on_exception(self, caplog) -> None:
        """scheduled_scan catches exceptions and logs ERROR without re-raising."""
        import logging

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with (
            patch("file_fetcher.app_runner.get_session", return_value=mock_session),
            patch("file_fetcher.app_runner.settings_service") as mock_svc,
            patch("file_fetcher.app_runner.run_full_scan", side_effect=RuntimeError("boom")),
            caplog.at_level(logging.ERROR, logger="file_fetcher.app_runner"),
        ):
            mock_svc.get.return_value = "true"

            from file_fetcher.app_runner import scheduled_scan

            scheduled_scan()  # Must NOT raise

        assert "scheduled_scan" in caplog.text


# ── scheduled_enrich() ────────────────────────────────────────────────────────


class TestScheduledEnrich:
    def test_enrich_runs_with_correct_params(self) -> None:
        """scheduled_enrich reads batch_limit/daily_quota from settings and calls enrichment."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with (
            patch("file_fetcher.app_runner.get_session", return_value=mock_session),
            patch("file_fetcher.app_runner.settings_service") as mock_svc,
            patch("file_fetcher.app_runner.run_enrichment_batch") as mock_enrich,
        ):
            mock_svc.get.side_effect = lambda s, k, d=None: {"omdb_batch_limit": "25", "omdb_daily_quota": "500"}.get(k, d)

            from file_fetcher.app_runner import scheduled_enrich

            scheduled_enrich()

        mock_enrich.assert_called_once_with(mock_session, batch_limit=25, daily_quota=500)

    def test_enrich_logs_error_on_exception(self, caplog) -> None:
        """scheduled_enrich catches exceptions and logs ERROR without re-raising."""
        import logging

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with (
            patch("file_fetcher.app_runner.get_session", return_value=mock_session),
            patch("file_fetcher.app_runner.settings_service") as mock_svc,
            patch("file_fetcher.app_runner.run_enrichment_batch", side_effect=RuntimeError("fail")),
            caplog.at_level(logging.ERROR, logger="file_fetcher.app_runner"),
        ):
            mock_svc.get.return_value = "50"

            from file_fetcher.app_runner import scheduled_enrich

            scheduled_enrich()  # Must NOT raise

        assert "scheduled_enrich" in caplog.text


# ── main() ────────────────────────────────────────────────────────────────────


class TestMain:
    def test_main_initialises_and_starts_scheduler(self) -> None:
        """main() calls initialize_app, registers 2 jobs, starts scheduler, and blocks."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_scheduler = MagicMock()
        mock_event = MagicMock()
        # Simulate blocking then returning (to avoid infinite wait in tests)
        mock_event_instance = MagicMock()
        mock_event.return_value = mock_event_instance

        with (
            patch("file_fetcher.app_runner.initialize_app") as mock_init,
            patch("file_fetcher.app_runner.get_session", return_value=mock_session),
            patch("file_fetcher.app_runner.settings_service") as mock_svc,
            patch("file_fetcher.app_runner.BackgroundScheduler", return_value=mock_scheduler),
            patch("file_fetcher.app_runner.Event", mock_event),
        ):
            mock_svc.get.side_effect = lambda s, k, d=None: {
                "sftp_scan_cron": "0 3 * * *",
                "omdb_enrich_cron": "0 4 * * *",
            }.get(k, d)

            from file_fetcher.app_runner import main

            main()

        mock_init.assert_called_once()
        assert mock_scheduler.add_job.call_count == 2
        mock_scheduler.start.assert_called_once()
        mock_event_instance.wait.assert_called_once()

    def test_main_registers_scan_and_enrich_jobs(self) -> None:
        """main() registers jobs with ids 'scan' and 'enrich'."""
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        mock_scheduler = MagicMock()
        registered_ids: list[str] = []

        def capture_add_job(fn, trigger, id, **kwargs):
            registered_ids.append(id)

        mock_scheduler.add_job.side_effect = capture_add_job
        mock_event_instance = MagicMock()

        with (
            patch("file_fetcher.app_runner.initialize_app"),
            patch("file_fetcher.app_runner.get_session", return_value=mock_session),
            patch("file_fetcher.app_runner.settings_service") as mock_svc,
            patch("file_fetcher.app_runner.BackgroundScheduler", return_value=mock_scheduler),
            patch("file_fetcher.app_runner.Event", return_value=mock_event_instance),
        ):
            mock_svc.get.side_effect = lambda s, k, d=None: {
                "sftp_scan_cron": "0 3 * * *",
                "omdb_enrich_cron": "0 4 * * *",
            }.get(k, d)

            from file_fetcher.app_runner import main

            main()

        assert "scan" in registered_ids
        assert "enrich" in registered_ids
