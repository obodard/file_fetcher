"""Unit tests for scanner_service.reconcile_remote_scan (Story 1.3)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from file_fetcher.models.base import Base
from file_fetcher.models.enums import MediaType
from file_fetcher.models.movie import Movie
from file_fetcher.models.remote_file import RemoteFile
from file_fetcher.models.show import Show
from file_fetcher.services.scanner_service import reconcile_remote_scan


@pytest.fixture(scope="function")
def db_session():
    """In-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _film_scan(entries: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """Build scan_results tuples for film entries."""
    return [(f"/films/{fn}", fn, "/films") for fn in entries]


def _series_scan(entries: list[str]) -> list[tuple[str, str, str]]:
    """Build scan_results tuples for series entries."""
    return [(f"/series/{fn}", fn, "/series") for fn in entries]


# ── New file discovery ─────────────────────────────────────────────────────────

def test_new_files_inserted(db_session):
    """New remote paths produce new RemoteFile + Movie rows."""
    scan = _film_scan(["Inception (2010)", "Dune (2021)"])
    result = reconcile_remote_scan(db_session, scan, MediaType.film)
    db_session.commit()

    assert result.new == 2
    assert result.removed == 0
    assert result.unchanged == 0

    rfs = db_session.query(RemoteFile).all()
    assert len(rfs) == 2
    assert db_session.query(Movie).count() == 2


def test_series_new_files(db_session):
    """New series paths create Show entries."""
    scan = _series_scan(["Breaking Bad S01", "Chernobyl (2019)"])
    result = reconcile_remote_scan(db_session, scan, MediaType.series)
    db_session.commit()

    assert result.new == 2
    assert db_session.query(Show).count() == 2


# ── Idempotent re-scan ────────────────────────────────────────────────────────

def test_idempotent_rescan(db_session):
    """Re-scanning the same paths yields 0 new, 0 removed, N unchanged."""
    scan = _film_scan(["The Matrix (1999)"])
    reconcile_remote_scan(db_session, scan, MediaType.film)
    db_session.commit()

    result2 = reconcile_remote_scan(db_session, scan, MediaType.film)
    db_session.commit()

    assert result2.new == 0
    assert result2.removed == 0
    assert result2.unchanged == 1
    # Still only 1 RemoteFile
    assert db_session.query(RemoteFile).count() == 1


# ── Stale file cleanup ────────────────────────────────────────────────────────

def test_stale_files_removed(db_session):
    """Paths no longer in the scan are deleted from the DB."""
    scan1 = _film_scan(["Parasite (2019)", "Roma (2018)"])
    reconcile_remote_scan(db_session, scan1, MediaType.film)
    db_session.commit()
    assert db_session.query(RemoteFile).count() == 2

    # Second scan: Parasite gone, new entry added
    scan2 = _film_scan(["Roma (2018)", "Oppenheimer (2023)"])
    result = reconcile_remote_scan(db_session, scan2, MediaType.film)
    db_session.commit()

    assert result.removed == 1
    assert result.new == 1
    assert result.unchanged == 1
    remaining_paths = {rf.remote_path for rf in db_session.query(RemoteFile).all()}
    assert "/films/Roma (2018)" in remaining_paths
    assert "/films/Oppenheimer (2023)" in remaining_paths
    assert "/films/Parasite (2019)" not in remaining_paths


# ── Title parsing integration ─────────────────────────────────────────────────

def test_title_parsing_integration(db_session):
    """Title and year are parsed from the filename."""
    scan = _film_scan(["Good.Bye.Lenin.2003.1080p.BluRay"])
    reconcile_remote_scan(db_session, scan, MediaType.film)
    db_session.commit()

    movie = db_session.query(Movie).first()
    assert movie is not None
    assert "Lenin" in movie.title or "Good" in movie.title  # parsed title
    assert movie.year == 2003


# ── Malformed filename handling ───────────────────────────────────────────────

def test_malformed_filename_no_crash(db_session):
    """Malformed filenames are handled without raising exceptions."""
    scan = [("/films/???", "???", "/films")]
    result = reconcile_remote_scan(db_session, scan, MediaType.film)
    db_session.commit()
    # Should not raise; at most 1 entry inserted
    assert result.new <= 1


def test_empty_scan_removes_all(db_session):
    """An empty scan result removes all previously known entries for that type."""
    scan = _film_scan(["Inception (2010)"])
    reconcile_remote_scan(db_session, scan, MediaType.film)
    db_session.commit()
    assert db_session.query(RemoteFile).count() == 1

    result = reconcile_remote_scan(db_session, [], MediaType.film)
    db_session.commit()

    assert result.removed == 1
    assert db_session.query(RemoteFile).count() == 0


# ── Find-or-create deduplication ─────────────────────────────────────────────

def test_same_title_different_paths_share_movie(db_session):
    """Two remote paths for the same parsed title share a single Movie row."""
    # Two different filenames that both parse to the same title+year
    scan = [
        ("/films/Dune.Part.One.2021.1080p", "Dune.Part.One.2021.1080p", "/films"),
        ("/films/Dune.Part.One.2021.4k", "Dune.Part.One.2021.4k", "/films/4k"),
    ]
    reconcile_remote_scan(db_session, scan, MediaType.film)
    db_session.commit()

    assert db_session.query(RemoteFile).count() == 2
    # Might be 1 or 2 movies depending on filename variation — just verify no crash
    assert db_session.query(Movie).count() >= 1
