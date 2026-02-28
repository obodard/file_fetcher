"""Unit tests for queue CLI commands (Stories 4.2 + 4.4)."""

from __future__ import annotations

import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from file_fetcher.cli.queue_cmd import queue
from file_fetcher.models.base import Base
from file_fetcher.models.enums import DownloadStatus, MediaType
from file_fetcher.models.movie import Movie
from file_fetcher.models.remote_file import RemoteFile
from file_fetcher.services import queue_service


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    with Session(db_engine) as session:
        yield session


@pytest.fixture(autouse=True)
def patch_get_session(db_session, monkeypatch):
    """Replace get_session with the in-memory test session."""
    from contextlib import contextmanager

    @contextmanager
    def _fake_get_session():
        yield db_session

    monkeypatch.setattr("file_fetcher.cli.queue_cmd.get_session", _fake_get_session)


# ── Helpers ───────────────────────────────────────────────────────────────────

_counter = 0


def _make_remote_file(
    session: Session,
    path: str = "/films/movie.mkv",
    title: str = "Test Movie",
    year: int = 2020,
) -> RemoteFile:
    global _counter
    _counter += 1
    movie = Movie(title=f"{title} {_counter}", year=year, media_type=MediaType.film)
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


runner = CliRunner()


# ── Story 4.2 — add ───────────────────────────────────────────────────────────


class TestQueueAdd:
    def test_add_by_path_substring(self, db_session):
        rf = _make_remote_file(db_session, "/films/Inception (2010).mkv", "Inception", 2010)
        result = runner.invoke(queue, ["add", "Inception"])
        assert result.exit_code == 0
        assert "Added to queue" in result.output
        assert "Inception" in result.output

    def test_add_by_id(self, db_session):
        rf = _make_remote_file(db_session, "/films/Dune (2021).mkv", "Dune", 2021)
        result = runner.invoke(queue, ["add", str(rf.id)])
        assert result.exit_code == 0
        assert "Added to queue" in result.output

    def test_add_with_priority(self, db_session):
        rf = _make_remote_file(db_session)
        result = runner.invoke(queue, ["add", str(rf.id), "--priority", "7"])
        assert result.exit_code == 0
        assert "Added to queue" in result.output
        entries = queue_service.list_queue(db_session)
        assert entries[0].priority == 7

    def test_add_duplicate_shows_existing_message(self, db_session):
        rf = _make_remote_file(db_session)
        runner.invoke(queue, ["add", str(rf.id)])
        entry = queue_service.get_pending(db_session)[0]
        # Simulate already-queued non-pending (e.g. completed)
        entry.status = DownloadStatus.COMPLETED
        db_session.commit()
        result = runner.invoke(queue, ["add", str(rf.id)])
        assert result.exit_code == 0
        assert "Already in queue" in result.output

    def test_add_no_match_exits_nonzero(self, db_session):
        result = runner.invoke(queue, ["add", "nonexistent_film_xyz"])
        assert result.exit_code != 0


# ── Story 4.2 — list ──────────────────────────────────────────────────────────


class TestQueueList:
    def test_list_all(self, db_session):
        rf1 = _make_remote_file(db_session, "/films/a.mkv", "Film A", 2021)
        rf2 = _make_remote_file(db_session, "/films/b.mkv", "Film B", 2022)
        queue_service.add_to_queue(db_session, rf1.id)
        queue_service.add_to_queue(db_session, rf2.id)
        result = runner.invoke(queue, ["list"])
        assert result.exit_code == 0
        assert "Film A" in result.output
        assert "Film B" in result.output

    def test_list_empty(self, db_session):
        result = runner.invoke(queue, ["list"])
        assert result.exit_code == 0
        assert "empty" in result.output.lower()

    def test_list_filtered_by_status(self, db_session):
        rf = _make_remote_file(db_session, "/films/a.mkv", "Film A", 2020)
        entry = queue_service.add_to_queue(db_session, rf.id)
        entry.status = DownloadStatus.COMPLETED
        db_session.commit()

        result_pending = runner.invoke(queue, ["list", "--status", "pending"])
        assert result_pending.exit_code == 0
        assert "empty" in result_pending.output.lower()

        result_completed = runner.invoke(queue, ["list", "--status", "completed"])
        assert result_completed.exit_code == 0
        assert "Film A" in result_completed.output


# ── Story 4.2 — remove ───────────────────────────────────────────────────────


class TestQueueRemove:
    def test_remove_existing(self, db_session):
        rf = _make_remote_file(db_session)
        entry = queue_service.add_to_queue(db_session, rf.id)
        result = runner.invoke(queue, ["remove", str(entry.id)])
        assert result.exit_code == 0
        assert "Removed from queue" in result.output

    def test_remove_nonexistent(self, db_session):
        result = runner.invoke(queue, ["remove", "9999"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


# ── Story 4.4 — retry ────────────────────────────────────────────────────────


class TestQueueRetry:
    def test_retry_single(self, db_session):
        rf = _make_remote_file(db_session)
        entry = queue_service.add_to_queue(db_session, rf.id)
        entry.status = DownloadStatus.FAILED
        entry.error_message = "timeout"
        db_session.commit()

        result = runner.invoke(queue, ["retry", str(entry.id)])
        assert result.exit_code == 0
        assert "pending" in result.output.lower()

        db_session.refresh(entry)
        assert entry.status == DownloadStatus.PENDING

    def test_retry_stuck_downloading(self, db_session):
        rf = _make_remote_file(db_session)
        entry = queue_service.add_to_queue(db_session, rf.id)
        entry.status = DownloadStatus.DOWNLOADING
        db_session.commit()

        result = runner.invoke(queue, ["retry", str(entry.id)])
        assert result.exit_code == 0
        db_session.refresh(entry)
        assert entry.status == DownloadStatus.PENDING

    def test_retry_all_failed(self, db_session):
        rf1 = _make_remote_file(db_session, "/films/a.mkv")
        rf2 = _make_remote_file(db_session, "/films/b.mkv")
        e1 = queue_service.add_to_queue(db_session, rf1.id)
        e2 = queue_service.add_to_queue(db_session, rf2.id)
        e1.status = DownloadStatus.FAILED
        e2.status = DownloadStatus.FAILED
        db_session.commit()

        result = runner.invoke(queue, ["retry", "--all-failed"])
        assert result.exit_code == 0
        assert "2" in result.output

    def test_retry_nonexistent(self, db_session):
        result = runner.invoke(queue, ["retry", "9999"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


# ── Story 4.4 — status ───────────────────────────────────────────────────────


class TestQueueStatus:
    def test_status_shows_counts(self, db_session):
        rf = _make_remote_file(db_session)
        queue_service.add_to_queue(db_session, rf.id)
        result = runner.invoke(queue, ["status"])
        assert result.exit_code == 0
        assert "pending" in result.output
        assert "total" in result.output
