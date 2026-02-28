"""Unit tests for cli/scan.py master switch (Story 1.4)."""

from __future__ import annotations

import sys
import pytest


def test_scan_disabled_exits_cleanly(monkeypatch, capsys):
    """When SFTP_SCAN_ENABLED=false, run_scan exits 0 without attempting any connection."""
    monkeypatch.setenv("SFTP_SCAN_ENABLED", "false")

    from file_fetcher.cli.scan import _scan_enabled, run_scan

    # _scan_enabled should return False
    assert _scan_enabled() is False

    # run_scan should exit 0
    with pytest.raises(SystemExit) as exc_info:
        run_scan()
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "disabled" in captured.out.lower()


def test_scan_enabled_by_default(monkeypatch):
    """When SFTP_SCAN_ENABLED is not set, scanning is enabled."""
    monkeypatch.delenv("SFTP_SCAN_ENABLED", raising=False)

    from file_fetcher.cli.scan import _scan_enabled
    assert _scan_enabled() is True


def test_scan_enabled_true_value(monkeypatch):
    """SFTP_SCAN_ENABLED=true means scanning is enabled."""
    monkeypatch.setenv("SFTP_SCAN_ENABLED", "true")
    from file_fetcher.cli.scan import _scan_enabled
    assert _scan_enabled() is True


def test_scan_enabled_false_value(monkeypatch):
    """SFTP_SCAN_ENABLED=false means scanning is disabled."""
    monkeypatch.setenv("SFTP_SCAN_ENABLED", "false")
    from file_fetcher.cli.scan import _scan_enabled
    assert _scan_enabled() is False


def test_scan_enabled_case_insensitive(monkeypatch):
    """SFTP_SCAN_ENABLED check is case-insensitive."""
    monkeypatch.setenv("SFTP_SCAN_ENABLED", "FALSE")
    from file_fetcher.cli.scan import _scan_enabled
    assert _scan_enabled() is False

    monkeypatch.setenv("SFTP_SCAN_ENABLED", "True")
    # Re-import to pick up env change
    import importlib
    import file_fetcher.cli.scan as scan_mod
    importlib.reload(scan_mod)
    assert scan_mod._scan_enabled() is True


def test_no_sftp_host_exits_with_error(monkeypatch, capsys):
    """When SFTP_HOST is empty and scan is enabled, run_scan exits with status 1."""
    monkeypatch.setenv("SFTP_SCAN_ENABLED", "true")
    monkeypatch.delenv("SFTP_HOST", raising=False)

    from file_fetcher.cli.scan import run_scan

    with pytest.raises(SystemExit) as exc_info:
        run_scan()
    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    assert "sftp_host" in captured.err.lower() or "sftp_host" in captured.out.lower()
