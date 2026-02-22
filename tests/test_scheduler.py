"""Tests for file_fetcher.scheduler."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

from file_fetcher.scheduler import wait_until


def test_wait_until_none_returns_immediately() -> None:
    """No schedule → return instantly, no sleep."""
    with patch("file_fetcher.scheduler.time.sleep") as mock_sleep:
        wait_until(None)
        mock_sleep.assert_not_called()


def test_wait_until_past_returns_immediately(
    capsys: "pytest.CaptureFixture[str]",
) -> None:
    """Past time → print message and return, no sleep."""
    past = datetime.now() - timedelta(hours=1)
    with patch("file_fetcher.scheduler.time.sleep") as mock_sleep:
        wait_until(past)
        mock_sleep.assert_not_called()
    assert "already passed" in capsys.readouterr().out.lower()


def test_wait_until_future_sleeps(
    capsys: "pytest.CaptureFixture[str]",
) -> None:
    """Future time → sleep for the correct duration."""
    future = datetime.now() + timedelta(seconds=120)
    with patch("file_fetcher.scheduler.time.sleep") as mock_sleep:
        wait_until(future)
        mock_sleep.assert_called_once()
        slept = mock_sleep.call_args[0][0]
        # Should be roughly 120s (allow 5s tolerance for test execution time)
        assert 115 <= slept <= 125

    out = capsys.readouterr().out
    assert "waiting" in out.lower()
    assert "scheduled time reached" in out.lower()


def test_wait_until_keyboard_interrupt() -> None:
    """Ctrl+C during wait → SystemExit."""
    future = datetime.now() + timedelta(hours=1)
    with patch(
        "file_fetcher.scheduler.time.sleep", side_effect=KeyboardInterrupt
    ):
        try:
            wait_until(future)
            assert False, "Should have raised SystemExit"
        except SystemExit as exc:
            assert exc.code == 0
