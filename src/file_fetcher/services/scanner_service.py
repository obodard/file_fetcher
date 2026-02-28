"""Scanner service — reconciles SFTP scan results with the database catalog."""

from __future__ import annotations

import logging
from typing import NamedTuple

from sqlalchemy.orm import Session

from file_fetcher.models.enums import MediaType
from file_fetcher.models.movie import Movie
from file_fetcher.models.remote_file import RemoteFile
from file_fetcher.models.show import Show
from file_fetcher.title_parser import parse_title_and_year

log = logging.getLogger(__name__)


class ReconcileResult(NamedTuple):
    new: int
    removed: int
    unchanged: int


def _find_or_create_movie(session: Session, title: str, year: int | None) -> Movie:
    """Return existing Movie or create a new one."""
    movie = session.query(Movie).filter_by(title=title, year=year).first()
    if movie is None:
        movie = Movie(title=title, year=year, media_type=MediaType.film)
        session.add(movie)
        session.flush()  # populate id without committing
    return movie


def _find_or_create_show(session: Session, title: str, year: int | None) -> Show:
    """Return existing Show or create a new one."""
    show = session.query(Show).filter_by(title=title, year=year).first()
    if show is None:
        show = Show(title=title, year=year, media_type=MediaType.series)
        session.add(show)
        session.flush()
    return show


def reconcile_remote_scan(
    session: Session,
    scan_results: list[tuple[str, str, str]],
    media_type: MediaType,
) -> ReconcileResult:
    """Insert new RemoteFile entries, remove stale ones, leave unchanged entries untouched.

    Args:
        session:      Active SQLAlchemy session (caller commits).
        scan_results: List of ``(remote_path, filename, source_directory)`` tuples
                      from the SFTP scanner for this media_type.
        media_type:   ``MediaType.film`` or ``MediaType.series``.

    Returns:
        ``ReconcileResult(new, removed, unchanged)`` counts.
    """
    # Fetch all existing remote_path values for this media_type in one query
    existing_rows: list[RemoteFile] = (
        session.query(RemoteFile)
        .filter(RemoteFile.media_type == media_type)
        .all()
    )
    existing_by_path: dict[str, RemoteFile] = {rf.remote_path: rf for rf in existing_rows}

    scan_paths = {remote_path for remote_path, _, _ in scan_results}

    # ── Remove stale paths ────────────────────────────────────────────────────
    stale_paths = set(existing_by_path.keys()) - scan_paths
    removed = 0
    for path in stale_paths:
        session.delete(existing_by_path[path])
        removed += 1

    # ── Insert new paths ─────────────────────────────────────────────────────
    new_count = 0
    unchanged = 0
    for remote_path, filename, source_directory in scan_results:
        if remote_path in existing_by_path:
            unchanged += 1
            continue

        title, year = _safe_parse(filename)

        if media_type == MediaType.film:
            entity = _find_or_create_movie(session, title, year)
            remote_file = RemoteFile(
                remote_path=remote_path,
                filename=filename,
                media_type=media_type,
                source_directory=source_directory,
                movie_id=entity.id,
            )
        else:
            entity = _find_or_create_show(session, title, year)
            remote_file = RemoteFile(
                remote_path=remote_path,
                filename=filename,
                media_type=media_type,
                source_directory=source_directory,
                show_id=entity.id,
            )

        session.add(remote_file)
        new_count += 1

    # Batch flush (caller commits)
    session.flush()

    log.info(
        f"reconcile_remote_scan [{media_type.value}]: "
        f"new={new_count} removed={removed} unchanged={unchanged}"
    )
    return ReconcileResult(new=new_count, removed=removed, unchanged=unchanged)


def _safe_parse(filename: str) -> tuple[str, int | None]:
    """Parse title and year, falling back to the raw filename on error."""
    try:
        return parse_title_and_year(filename)
    except Exception as exc:  # pragma: no cover
        log.warning(f"Failed to parse filename {filename!r}: {exc}")
        return filename, None


def run_full_scan(session: Session) -> None:
    """High-level scan that reads SFTP paths from the environment and reconciles the DB.

    Reads ``SFTP_HOST``, ``SFTP_PORT``, ``SFTP_USER``, ``SFTP_PASSWORD``,
    ``SFTP_FILMS_PATH``, and ``SFTP_SERIES_PATH`` from the process environment
    (already loaded by :func:`file_fetcher.bootstrap.initialize_app`).

    Silently skips each path when the env var is empty or the SFTP connection
    fails, logging a warning instead of raising.

    Args:
        session: Active SQLAlchemy session (caller commits).
    """
    import os

    import paramiko

    from file_fetcher.scanner import scan_remote_path

    sftp_host = os.environ.get("SFTP_HOST", "")
    sftp_port = int(os.environ.get("SFTP_PORT", "22"))
    sftp_user = os.environ.get("SFTP_USER", "")
    sftp_password = os.environ.get("SFTP_PASSWORD", "")
    films_path = os.environ.get("SFTP_FILMS_PATH", "")
    series_path = os.environ.get("SFTP_SERIES_PATH", "")

    if not sftp_host:
        log.warning("run_full_scan: SFTP_HOST not set — skipping scan.")
        return

    transport: paramiko.Transport | None = None
    sftp_client = None
    try:
        transport = paramiko.Transport((sftp_host, sftp_port))
        transport.connect(username=sftp_user, password=sftp_password)
        sftp_client = paramiko.SFTPClient.from_transport(transport)

        if films_path:
            try:
                films_results = scan_remote_path(sftp_client, films_path)
                reconcile_remote_scan(session, films_results, MediaType.film)
            except Exception as exc:
                log.warning(f"run_full_scan: films scan failed: {exc}")

        if series_path:
            try:
                series_results = scan_remote_path(sftp_client, series_path)
                reconcile_remote_scan(session, series_results, MediaType.series)
            except Exception as exc:
                log.warning(f"run_full_scan: series scan failed: {exc}")

    except Exception as exc:
        log.error(f"run_full_scan: SFTP connection error: {exc}")
    finally:
        if sftp_client:
            sftp_client.close()
        if transport:
            transport.close()
