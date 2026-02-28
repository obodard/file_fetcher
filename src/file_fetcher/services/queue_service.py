"""Queue service — manages the download queue in the database."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, update
from sqlalchemy.orm import Session, joinedload

from file_fetcher.models.download_queue import DownloadQueue
from file_fetcher.models.enums import DownloadStatus
from file_fetcher.models.remote_file import RemoteFile

log = logging.getLogger(__name__)


# ── Story 4.1 ─────────────────────────────────────────────────────────────────


def add_to_queue(
    session: Session,
    remote_file_id: int,
    priority: int = 0,
) -> DownloadQueue:
    """Add a RemoteFile to the download queue.

    Returns the existing entry if already queued (idempotent).
    Raises ValueError if remote_file_id does not exist.
    """
    if session.get(RemoteFile, remote_file_id) is None:
        raise ValueError(f"RemoteFile with id={remote_file_id} not found.")

    existing = (
        session.query(DownloadQueue)
        .filter_by(remote_file_id=remote_file_id)
        .first()
    )
    if existing is not None:
        return existing

    entry = DownloadQueue(
        remote_file_id=remote_file_id,
        priority=priority,
        status=DownloadStatus.PENDING,
    )
    session.add(entry)
    session.commit()
    return entry


def list_queue(
    session: Session,
    status: Optional[DownloadStatus] = None,
) -> list[DownloadQueue]:
    """Return queue entries ordered by priority desc, created_at asc.

    Args:
        session: Active SQLAlchemy session.
        status:  If provided, only return entries with this status.
    """
    query = session.query(DownloadQueue).options(
        joinedload(DownloadQueue.remote_file)
    )
    if status is not None:
        query = query.filter(DownloadQueue.status == status)
    return (
        query.order_by(
            DownloadQueue.priority.desc(),  # type: ignore[union-attr]
            DownloadQueue.created_at.asc(),  # type: ignore[union-attr]
        )
        .all()
    )


def remove_from_queue(session: Session, queue_id: int) -> None:
    """Delete a queue entry by ID.

    Raises ValueError if the entry does not exist.
    """
    entry = session.get(DownloadQueue, queue_id)
    if entry is None:
        raise ValueError(f"Queue entry #{queue_id} not found.")
    session.delete(entry)
    session.commit()


def get_pending(session: Session) -> list[DownloadQueue]:
    """Return all pending entries ordered by priority desc, created_at asc."""
    return list_queue(session, status=DownloadStatus.PENDING)


# ── Story 4.4 ─────────────────────────────────────────────────────────────────


def retry_entry(session: Session, queue_id: int) -> DownloadQueue:
    """Reset a queue entry (any status) back to pending.

    Clears error_message and started_at.
    Raises ValueError if the entry does not exist.
    """
    entry = session.get(DownloadQueue, queue_id)
    if entry is None:
        raise ValueError(f"Queue entry #{queue_id} not found.")

    entry.status = DownloadStatus.PENDING
    entry.error_message = None
    entry.started_at = None
    session.commit()
    return entry


def retry_all_failed(session: Session) -> int:
    """Reset all failed entries to pending.

    Returns the number of rows updated.
    """
    result = session.execute(
        update(DownloadQueue)
        .where(DownloadQueue.status == DownloadStatus.FAILED)
        .values(
            status=DownloadStatus.PENDING,
            error_message=None,
            started_at=None,
        )
    )
    session.commit()
    return result.rowcount  # type: ignore[attr-defined]


def get_queue_summary(session: Session) -> dict[str, int]:
    """Return status counts for every DownloadStatus plus a total.

    Returns a dict like::

        {"pending": 3, "downloading": 0, "completed": 10, "failed": 1, "total": 14}
    """
    rows = (
        session.query(DownloadQueue.status, func.count().label("cnt"))
        .group_by(DownloadQueue.status)
        .all()
    )
    summary: dict[str, int] = {s.value: 0 for s in DownloadStatus}
    for status, count in rows:
        key = status.value if isinstance(status, DownloadStatus) else status
        summary[key] = count
    summary["total"] = sum(summary.values())
    return summary
