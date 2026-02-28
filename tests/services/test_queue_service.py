"""Unit tests for queue_service (Stories 4.1 + 4.4)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from file_fetcher.models.base import Base
from file_fetcher.models.download_queue import DownloadQueue
from file_fetcher.models.enums import DownloadStatus, MediaType
from file_fetcher.models.movie import Movie
from file_fetcher.models.remote_file import RemoteFile
from file_fetcher.services import queue_service


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="function")
def db_session():
    """In-memory SQLite session with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


_counter = 0


def _make_remote_file(session: Session, path: str = "/films/movie.mkv") -> RemoteFile:
    """Create and flush a RemoteFile with a uniquely-titled linked Movie."""
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
    return rf


# ── Story 4.1 tests ───────────────────────────────────────────────────────────


class TestAddToQueue:
    def test_add_creates_entry(self, db_session):
        rf = _make_remote_file(db_session)
        entry = queue_service.add_to_queue(db_session, rf.id)
        assert entry.id is not None
        assert entry.remote_file_id == rf.id
        assert entry.status == DownloadStatus.PENDING
        assert entry.priority == 0

    def test_add_with_priority(self, db_session):
        rf = _make_remote_file(db_session)
        entry = queue_service.add_to_queue(db_session, rf.id, priority=5)
        assert entry.priority == 5

    def test_add_duplicate_returns_existing(self, db_session):
        rf = _make_remote_file(db_session)
        entry1 = queue_service.add_to_queue(db_session, rf.id)
        entry2 = queue_service.add_to_queue(db_session, rf.id)
        assert entry1.id == entry2.id

    def test_add_invalid_remote_file_raises(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            queue_service.add_to_queue(db_session, remote_file_id=9999)


class TestListQueue:
    def test_list_all_returns_all_entries(self, db_session):
        rf1 = _make_remote_file(db_session, "/films/a.mkv")
        rf2 = _make_remote_file(db_session, "/films/b.mkv")
        queue_service.add_to_queue(db_session, rf1.id)
        queue_service.add_to_queue(db_session, rf2.id)
        entries = queue_service.list_queue(db_session)
        assert len(entries) == 2

    def test_list_filtered_by_status(self, db_session):
        rf = _make_remote_file(db_session)
        entry = queue_service.add_to_queue(db_session, rf.id)
        # Manually set one to completed
        entry.status = DownloadStatus.COMPLETED
        db_session.commit()

        pending = queue_service.list_queue(db_session, status=DownloadStatus.PENDING)
        completed = queue_service.list_queue(db_session, status=DownloadStatus.COMPLETED)

        assert len(pending) == 0
        assert len(completed) == 1

    def test_list_no_n_plus_one(self, db_session):
        """Joined remote_file is accessible without extra queries."""
        rf = _make_remote_file(db_session)
        queue_service.add_to_queue(db_session, rf.id)
        entries = queue_service.list_queue(db_session)
        assert entries[0].remote_file.remote_path == rf.remote_path

    def test_list_order_priority_desc_then_created_asc(self, db_session):
        rf1 = _make_remote_file(db_session, "/films/low.mkv")
        rf2 = _make_remote_file(db_session, "/films/high.mkv")
        e1 = queue_service.add_to_queue(db_session, rf1.id, priority=0)
        e2 = queue_service.add_to_queue(db_session, rf2.id, priority=10)
        entries = queue_service.list_queue(db_session)
        assert entries[0].id == e2.id  # higher priority first
        assert entries[1].id == e1.id


class TestRemoveFromQueue:
    def test_remove_existing_entry(self, db_session):
        rf = _make_remote_file(db_session)
        entry = queue_service.add_to_queue(db_session, rf.id)
        queue_service.remove_from_queue(db_session, entry.id)
        remaining = queue_service.list_queue(db_session)
        assert len(remaining) == 0

    def test_remove_nonexistent_raises(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            queue_service.remove_from_queue(db_session, 9999)


class TestGetPending:
    def test_get_pending_returns_only_pending(self, db_session):
        rf1 = _make_remote_file(db_session, "/films/a.mkv")
        rf2 = _make_remote_file(db_session, "/films/b.mkv")
        e1 = queue_service.add_to_queue(db_session, rf1.id)
        e2 = queue_service.add_to_queue(db_session, rf2.id)
        e2.status = DownloadStatus.COMPLETED
        db_session.commit()
        pending = queue_service.get_pending(db_session)
        assert len(pending) == 1
        assert pending[0].id == e1.id

    def test_get_pending_ordering(self, db_session):
        rf1 = _make_remote_file(db_session, "/films/low.mkv")
        rf2 = _make_remote_file(db_session, "/films/high.mkv")
        e1 = queue_service.add_to_queue(db_session, rf1.id, priority=1)
        e2 = queue_service.add_to_queue(db_session, rf2.id, priority=5)
        pending = queue_service.get_pending(db_session)
        assert pending[0].id == e2.id


# ── Story 4.4 tests ───────────────────────────────────────────────────────────


class TestRetryEntry:
    def test_retry_resets_failed_to_pending(self, db_session):
        rf = _make_remote_file(db_session)
        entry = queue_service.add_to_queue(db_session, rf.id)
        entry.status = DownloadStatus.FAILED
        entry.error_message = "Connection refused"
        entry.started_at = None
        db_session.commit()

        retried = queue_service.retry_entry(db_session, entry.id)
        assert retried.status == DownloadStatus.PENDING
        assert retried.error_message is None

    def test_retry_resets_stuck_downloading(self, db_session):
        rf = _make_remote_file(db_session)
        entry = queue_service.add_to_queue(db_session, rf.id)
        entry.status = DownloadStatus.DOWNLOADING
        db_session.commit()

        retried = queue_service.retry_entry(db_session, entry.id)
        assert retried.status == DownloadStatus.PENDING

    def test_retry_nonexistent_raises(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            queue_service.retry_entry(db_session, 9999)


class TestRetryAllFailed:
    def test_retry_all_failed_resets_count(self, db_session):
        rf1 = _make_remote_file(db_session, "/films/a.mkv")
        rf2 = _make_remote_file(db_session, "/films/b.mkv")
        e1 = queue_service.add_to_queue(db_session, rf1.id)
        e2 = queue_service.add_to_queue(db_session, rf2.id)
        e1.status = DownloadStatus.FAILED
        e2.status = DownloadStatus.FAILED
        db_session.commit()

        count = queue_service.retry_all_failed(db_session)
        assert count == 2

        entries = queue_service.list_queue(db_session)
        for e in entries:
            assert e.status == DownloadStatus.PENDING

    def test_retry_all_failed_returns_zero_when_none(self, db_session):
        count = queue_service.retry_all_failed(db_session)
        assert count == 0


class TestGetQueueSummary:
    def test_summary_counts(self, db_session):
        rf1 = _make_remote_file(db_session, "/films/a.mkv")
        rf2 = _make_remote_file(db_session, "/films/b.mkv")
        rf3 = _make_remote_file(db_session, "/films/c.mkv")
        e1 = queue_service.add_to_queue(db_session, rf1.id)
        e2 = queue_service.add_to_queue(db_session, rf2.id)
        e3 = queue_service.add_to_queue(db_session, rf3.id)
        e2.status = DownloadStatus.COMPLETED
        e3.status = DownloadStatus.FAILED
        db_session.commit()

        summary = queue_service.get_queue_summary(db_session)
        assert summary["pending"] == 1
        assert summary["completed"] == 1
        assert summary["failed"] == 1
        assert summary["downloading"] == 0
        assert summary["total"] == 3

    def test_summary_empty_queue(self, db_session):
        summary = queue_service.get_queue_summary(db_session)
        assert summary["total"] == 0
        assert all(v == 0 for k, v in summary.items() if k != "total")
