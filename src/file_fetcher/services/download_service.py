"""Download service — transfers queued RemoteFiles via SFTP."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from file_fetcher.models.enums import DownloadStatus
from file_fetcher.services import queue_service

if TYPE_CHECKING:
    from file_fetcher.sftp_client import SFTPDownloader

log = logging.getLogger(__name__)


def process_queue(
    session: Session,
    downloader: "SFTPDownloader",
    download_dir: Path | str | None = None,
) -> dict[str, int]:
    """Download all pending queue entries via SFTP.

    For each pending entry:
      - Sets status → "downloading" + started_at, commits
      - Downloads file to DOWNLOAD_DIR preserving remote directory structure
      - On success: status → "completed" + completed_at
      - On failure: status → "failed" + error_message logged as WARNING

    Entries already in "downloading" state are skipped (WARNING logged).

    Args:
        session:      Active SQLAlchemy session.
        downloader:   Connected SFTPDownloader instance.
        download_dir: Override destination directory (defaults to DOWNLOAD_DIR env var
                      or ``./downloads``).

    Returns:
        Dict with keys ``succeeded``, ``failed``, ``skipped``.
    """
    if download_dir is None:
        download_dir = Path(os.environ.get("DOWNLOAD_DIR", "./downloads"))
    download_dir = Path(download_dir)

    # Warn about stuck "downloading" entries
    from file_fetcher.models.download_queue import DownloadQueue
    stuck = (
        session.query(DownloadQueue)
        .filter(DownloadQueue.status == DownloadStatus.DOWNLOADING)
        .all()
    )
    skipped = 0
    for entry in stuck:
        log.warning(
            "Queue entry #%d (remote_file_id=%d) is already in 'downloading' state — skipping.",
            entry.id,
            entry.remote_file_id,
        )
        skipped += 1

    pending = queue_service.get_pending(session)

    succeeded = 0
    failed = 0

    for entry in pending:
        remote_path = entry.remote_file.remote_path

        # ── Transition to downloading ──────────────────────────────────────
        entry.status = DownloadStatus.DOWNLOADING
        entry.started_at = datetime.now(timezone.utc)
        session.commit()

        print(f"  ⬇  Downloading: {remote_path}")

        # ── Resolve destination path ───────────────────────────────────────
        relative = Path(remote_path).relative_to("/") if remote_path.startswith("/") else Path(remote_path)
        local_path = download_dir / relative
        local_path.parent.mkdir(parents=True, exist_ok=True)

        # ── Transfer ───────────────────────────────────────────────────────
        try:
            downloader._download_file_with_retry(remote_path, local_path)
            entry.status = DownloadStatus.COMPLETED
            entry.completed_at = datetime.now(timezone.utc)
            session.commit()
            succeeded += 1
            print(f"  ✅  Completed: {remote_path}")
        except Exception as exc:  # noqa: BLE001
            entry.status = DownloadStatus.FAILED
            entry.error_message = str(exc)
            session.commit()
            failed += 1
            log.warning("Download failed for remote_file_id=%d: %s", entry.remote_file_id, exc)
            print(f"  ❌  Failed: {remote_path} — {exc}")

    return {"succeeded": succeeded, "failed": failed, "skipped": skipped}
