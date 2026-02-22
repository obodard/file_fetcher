"""Tests for file_fetcher.config."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from file_fetcher.config import load_config, _parse_file_list, _parse_schedule


# ── _parse_file_list ──────────────────────────────────────────────────────


def test_parse_file_list_basic(tmp_path: Path) -> None:
    flist = tmp_path / "files.txt"
    flist.write_text(
        "/remote/file1.mkv\n"
        "/remote/folder with spaces/\n"
        "/remote/file (2026).mp4\n"
    )
    result = _parse_file_list(flist)
    assert result == [
        "/remote/file1.mkv",
        "/remote/folder with spaces/",
        "/remote/file (2026).mp4",
    ]


def test_parse_file_list_skips_blanks_and_comments(tmp_path: Path) -> None:
    flist = tmp_path / "files.txt"
    flist.write_text(
        "# A comment\n"
        "\n"
        "/remote/file.mkv\n"
        "  \n"
        "# Another comment\n"
        "/remote/other.mkv\n"
    )
    result = _parse_file_list(flist)
    assert result == ["/remote/file.mkv", "/remote/other.mkv"]


def test_parse_file_list_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        _parse_file_list(tmp_path / "nonexistent.txt")


def test_parse_file_list_empty_warns(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    flist = tmp_path / "files.txt"
    flist.write_text("# Only comments\n")
    result = _parse_file_list(flist)
    assert result == []
    assert "empty" in capsys.readouterr().err.lower()


# ── _parse_schedule ───────────────────────────────────────────────────────


def test_parse_schedule_valid(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        schedule:
          date: "2026-03-01"
          time: "14:30"
        """)
    )
    dt = _parse_schedule(cfg)
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 3
    assert dt.day == 1
    assert dt.hour == 14
    assert dt.minute == 30


def test_parse_schedule_date_only(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        schedule:
          date: "2026-03-01"
        """)
    )
    dt = _parse_schedule(cfg)
    assert dt is not None
    assert dt.hour == 0
    assert dt.minute == 0


def test_parse_schedule_missing_file(tmp_path: Path) -> None:
    assert _parse_schedule(tmp_path / "nope.yaml") is None


def test_parse_schedule_no_section(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("# nothing here\n")
    assert _parse_schedule(cfg) is None


def test_parse_schedule_empty_section(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("schedule:\n")
    assert _parse_schedule(cfg) is None


def test_parse_schedule_invalid_format(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        textwrap.dedent("""\
        schedule:
          date: "not-a-date"
        """)
    )
    assert _parse_schedule(cfg) is None
    assert "invalid" in capsys.readouterr().err.lower()


# ── load_config (integration) ────────────────────────────────────────────


def test_load_config_full(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Create .env
    env = tmp_path / ".env"
    env.write_text(
        "SFTP_HOST=example.com\n"
        "SFTP_PORT=2222\n"
        "SFTP_USER=alice\n"
        "SFTP_PASSWORD=secret\n"
        f"FILE_LIST={tmp_path / 'files.txt'}\n"
        f"DOWNLOAD_DIR={tmp_path / 'dl'}\n"
    )

    # Create file list
    (tmp_path / "files.txt").write_text("/remote/file.mkv\n")

    # Create config
    cfg_yaml = tmp_path / "config.yaml"
    cfg_yaml.write_text(
        textwrap.dedent("""\
        schedule:
          date: "2026-06-15"
          time: "03:00"
        """)
    )

    # Clear any existing env vars to avoid leaking between tests
    monkeypatch.delenv("SFTP_HOST", raising=False)
    monkeypatch.delenv("SFTP_PORT", raising=False)
    monkeypatch.delenv("SFTP_USER", raising=False)
    monkeypatch.delenv("SFTP_PASSWORD", raising=False)
    monkeypatch.delenv("FILE_LIST", raising=False)
    monkeypatch.delenv("DOWNLOAD_DIR", raising=False)

    config = load_config(env_path=env, config_path=cfg_yaml)

    assert config.sftp_host == "example.com"
    assert config.sftp_port == 2222
    assert config.sftp_user == "alice"
    assert config.sftp_password == "secret"
    assert config.remote_paths == ["/remote/file.mkv"]
    assert config.scheduled_at is not None
    assert config.scheduled_at.year == 2026


def test_load_config_missing_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("SFTP_USER=alice\nSFTP_PASSWORD=secret\n")

    monkeypatch.delenv("SFTP_HOST", raising=False)

    with pytest.raises(SystemExit):
        load_config(env_path=env, config_path=tmp_path / "nope.yaml")
