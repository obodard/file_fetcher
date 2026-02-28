"""Unit tests for download_service (Story 4.3)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from file_fetcher.models.base import Base
from file_fetcher.models.download_queue import DownloadQueue
from file_fetcher.models.enums import DownloadStatus, MediaType
from file_fetcher.models.movie import Movie
from file_fetcher.models.remote_file import RemoteFile
from file_fetcher.services import download_service, queue_service


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def mock_downloader():
    """A mock SFTPDownloader that does nothing on _download_file_with_retry."""
    dl = MagicMock()
    dl._download_file_with_retry = MagicMock(return_value=None)
    return dl


_counter = 0


def _make_remote_file(
    session: Session,
    path: str = "/films/movie.mkv",
) -> RemoteFile:
    global _counter
    _counter += 1
    movie = Movie(title=f"Test Movie {_counter}", year=2020, media_type=MediaType.film)
    session.add(movie)
    session.flush()
    rf = RemoteFile(
        remote_path=path,
        filename=path.split("/")[-1],
        media_type=MediaType.film,
        movie_id=movie.id,
    )
    session.add(rf)
    session.flush()
    session.commit()
    return rf


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestProcessQueue:
    def test_successful_download_flow(self, db_session, mock_downloader, tmp_path):
        rf = _make_remote_file(db_session, "/films/movie.mkv")
        entry = queue_service.add_to_queue(db_session, rf.id)

        summary = download_service.process_queue(db_session, mock_downloader, tmp_path)

        assert summary["succeeded"] == 1
        assert summary["failed"] == 0
        assert summary["skipped"] == 0

        db_session.refresh(entry)
        assert entry.status == DownloadStatus.COMPLETED
        assert entry.completed_at is not None
        mock_downloader._download_file_with_retry.assert_called_once()

    def test_failure_sets_error_message(self, db_session, mock_downloader, tmp_path):
        rf = _make_remote_file(db_session, "/films/movie.mkv")
        entry = queue_service.add_to_queue(db_session, rf.id)
        mock_downloader._download_file_with_retry.side_effect = ConnectionError("SFTP timeout")

        summary = download_service.process_queue(db_session, mock_downloader, tmp_path)

        assert summary["succeeded"] == 0
        assert summary["failed"] == 1

        db_session.refresh(entry)
        assert entry.status == DownloadStatus.FAILED
        assert "SFTP timeout" in entry.error_message

    def test_skip_already_downloading(self, db_session, mock_downloader, tmp_path):
        rf = _make_remote_file(db_session, "/films/movie.mkv")
        entry = queue_service.add_to_queue(db_session, rf.id)
        # Manually set stuck
        entry.status = DownloadStatus.DOWNLOADING
        db_session.commit()

        summary = download_service.process_queue(db_session, mock_downloader, tmp_path)

        assert summary["skipped"] == 1
        assert summary["succeeded"] == 0
        mock_downloader._download_file_with_retry.assert_not_called()

    def test_queue_ordering_respected(self, db_session, mock_downloader, tmp_path):
        rf1 = _make_remote_file(db_session, "/films/low.mkv")
        rf2 = _make_remote_file(db_session, "/films/high.mkv")
        e1 = queue_service.add_to_queue(db_session, rf1.id, priority=0)
        e2 = queue_service.add_to_queue(db_session, rf2.id, priority=10)

        call_order: list[str] = []

        def fake_download(remote_path, local_path):
            call_order.append(remote_path)

        mock_downloader._download_file_with_retry.side_effect = fake_download

        download_service.process_queue(db_session, mock_downloader, tmp_path)

        # High priority (rf2) should be downloaded first
        assert call_order[0] == "/films/high.mkv"
        assert call_order[1] == "/films/low.mkv"

    def test_failure_continues_to_next_entry(self, db_session, mock_downloader, tmp_path):
        """A failed entry should not stop subsequent downloads."""
        rf1 = _make_remote_file(db_session, "/films/bad.mkv")
        rf2 = _make_remote_file(db_session, "/films/good.mkv")
        queue_service.add_to_queue(db_session, rf1.id, priority=10)
        queue_service.add_to_queue(db_session, rf2.id, priority=0)

        def side_effect(remote_path, local_path):
            if "bad" in remote_path:
                raise IOError("transfer failed")

        mock_downloader._download_file_with_retry.side_effect = side_effect

        summary = download_service.process_queue(db_session, mock_downloader, tmp_path)

        assert summary["succeeded"] == 1
        assert summary["failed"] == 1
