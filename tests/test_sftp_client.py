"""Tests for file_fetcher.sftp_client."""

from __future__ import annotations

import stat as stat_module
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from file_fetcher.config import AppConfig
from file_fetcher.sftp_client import SFTPDownloader


def _make_config(tmp_path: Path, remote_paths: list[str] | None = None) -> AppConfig:
    """Build a minimal AppConfig for testing."""
    return AppConfig(
        sftp_host="test.example.com",
        sftp_port=22,
        sftp_user="user",
        sftp_password="pass",
        file_list_path=tmp_path / "files.txt",
        download_dir=tmp_path / "dl",
        remote_paths=remote_paths or [],
        max_retries=2,
        retry_delay=0.01,  # fast retries for tests
    )


def _mock_stat(size: int, is_dir: bool = False) -> MagicMock:
    """Create a mock SFTPAttributes object."""
    st = MagicMock()
    st.st_size = size
    mode = stat_module.S_IFDIR | 0o755 if is_dir else stat_module.S_IFREG | 0o644
    st.st_mode = mode
    return st


class TestLocalPathFor:
    """Test the path-mapping logic."""

    def test_strips_leading_slash(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        dl = SFTPDownloader(config)
        result = dl._local_path_for("/remote/path/file.mkv")
        assert result == tmp_path / "dl" / "remote" / "path" / "file.mkv"

    def test_handles_spaces(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        dl = SFTPDownloader(config)
        result = dl._local_path_for("/path/My Movie (2026).mkv")
        assert result == tmp_path / "dl" / "path" / "My Movie (2026).mkv"


class TestDownloadFile:
    """Test single-file download logic (mocking SFTP)."""

    def test_skip_already_complete(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, ["/remote/file.mkv"])
        dl = SFTPDownloader(config)
        dl._sftp = MagicMock()

        # Simulate: remote is 1000 bytes, local is also 1000 bytes (complete)
        dl.sftp.stat.return_value = _mock_stat(1000)
        local_path = tmp_path / "dl" / "remote" / "file.mkv"
        local_path.parent.mkdir(parents=True)
        local_path.write_bytes(b"x" * 1000)

        dl._download_file("/remote/file.mkv", local_path)

        assert dl.skipped == 1
        assert dl.succeeded == 0
        dl.sftp.get.assert_not_called()

    def test_full_download(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path, ["/remote/file.mkv"])
        dl = SFTPDownloader(config)
        dl._sftp = MagicMock()

        # Remote file is 5000 bytes, no local file
        dl.sftp.stat.return_value = _mock_stat(5000)

        local_path = tmp_path / "dl" / "remote" / "file.mkv"

        dl._download_file("/remote/file.mkv", local_path)

        assert dl.succeeded == 1
        dl.sftp.get.assert_called_once()

    def test_resume_download(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        dl = SFTPDownloader(config)
        dl._sftp = MagicMock()

        # Remote is 5000 bytes, local is 2000 bytes (partial)
        dl.sftp.stat.return_value = _mock_stat(5000)
        local_path = tmp_path / "dl" / "file.mkv"
        local_path.parent.mkdir(parents=True)
        local_path.write_bytes(b"x" * 2000)

        # Simulate remote file read returning remaining 3000 bytes,
        # then empty to signal EOF
        mock_remote_file = MagicMock()
        mock_remote_file.read.side_effect = [b"y" * 3000, b""]
        mock_remote_file.__enter__ = MagicMock(return_value=mock_remote_file)
        mock_remote_file.__exit__ = MagicMock(return_value=False)

        dl.sftp.open.return_value = mock_remote_file

        with patch("file_fetcher.sftp_client.TransferProgress") as MockProg:
            mock_prog = MagicMock()
            MockProg.return_value.__enter__ = MagicMock(return_value=mock_prog)
            MockProg.return_value.__exit__ = MagicMock(return_value=False)
            dl._download_file("/remote/file.mkv", local_path)

        assert dl.succeeded == 1
        mock_remote_file.seek.assert_called_once_with(2000)


class TestRetry:
    """Test retry logic."""

    def test_retry_on_failure(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.max_retries = 3
        dl = SFTPDownloader(config)

        # First two calls fail, third succeeds
        dl._download_file = MagicMock(  # type: ignore[assignment]
            side_effect=[IOError("conn lost"), IOError("timeout"), None]
        )
        local_path = tmp_path / "dl" / "file.mkv"

        dl._download_file_with_retry("/remote/file.mkv", local_path)

        assert dl._download_file.call_count == 3  # type: ignore[attr-defined]
        assert dl.failed == 0  # succeeded on third try

    def test_retries_exhausted(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        config.max_retries = 2
        dl = SFTPDownloader(config)

        dl._download_file = MagicMock(  # type: ignore[assignment]
            side_effect=IOError("permanent failure")
        )
        local_path = tmp_path / "dl" / "file.mkv"

        dl._download_file_with_retry("/remote/file.mkv", local_path)

        assert dl._download_file.call_count == 2  # type: ignore[attr-defined]
        assert dl.failed == 1


class TestIsDir:
    """Test remote path type detection."""

    def test_detects_directory(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        dl = SFTPDownloader(config)
        dl._sftp = MagicMock()
        dl.sftp.stat.return_value = _mock_stat(0, is_dir=True)

        assert dl._is_dir("/some/path") is True

    def test_detects_file(self, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        dl = SFTPDownloader(config)
        dl._sftp = MagicMock()
        dl.sftp.stat.return_value = _mock_stat(1000, is_dir=False)

        assert dl._is_dir("/some/file.mkv") is False
