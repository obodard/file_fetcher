"""CLI command: file-fetcher scan

Scans the configured remote SFTP paths for films and series, then reconciles
the results with the database catalog.
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

from file_fetcher.db import get_session
from file_fetcher.models.enums import MediaType
from file_fetcher.services.scanner_service import reconcile_remote_scan

log = logging.getLogger(__name__)


def _scan_enabled() -> bool:
    """Return True unless SFTP_SCAN_ENABLED is explicitly set to 'false'."""
    return os.environ.get("SFTP_SCAN_ENABLED", "true").lower() != "false"


def run_scan() -> None:
    """Entry point for the `file-fetcher scan` command."""
    load_dotenv()

    if not _scan_enabled():
        print("SFTP scanning is disabled (SFTP_SCAN_ENABLED=false).")
        sys.exit(0)

    sftp_host = os.environ.get("SFTP_HOST", "")
    sftp_port = int(os.environ.get("SFTP_PORT", "22"))
    sftp_user = os.environ.get("SFTP_USER", "")
    sftp_password = os.environ.get("SFTP_PASSWORD", "")
    films_path = os.environ.get("SFTP_FILMS_PATH", "")
    series_path = os.environ.get("SFTP_SERIES_PATH", "")

    if not sftp_host:
        print("Error: SFTP_HOST is not configured.", file=sys.stderr)
        sys.exit(1)

    import paramiko
    from file_fetcher.scanner import scan_remote_path

    transport: paramiko.Transport | None = None
    sftp_client = None
    films_results: list[tuple[str, str, str]] = []
    series_results: list[tuple[str, str, str]] = []

    try:
        log.debug(f"Connecting to SFTP {sftp_host}:{sftp_port} as {sftp_user}")
        transport = paramiko.Transport((sftp_host, sftp_port))
        transport.connect(username=sftp_user, password=sftp_password)
        sftp_client = paramiko.SFTPClient.from_transport(transport)

        if films_path:
            try:
                films_results = scan_remote_path(sftp_client, films_path)
            except Exception as exc:
                log.warning(f"Films scan partial failure: {exc}")

        if series_path:
            try:
                series_results = scan_remote_path(sftp_client, series_path)
            except Exception as exc:
                log.warning(f"Series scan partial failure: {exc}")

    except Exception as exc:
        log.warning(f"SFTP connection failed: {exc}. Using partial results.")
    finally:
        if sftp_client:
            sftp_client.close()
        if transport:
            transport.close()

    # ── Reconcile with database ───────────────────────────────────────────────
    with get_session() as session:
        if films_path:
            film_result = reconcile_remote_scan(session, films_results, MediaType.film)
            print(
                f"Films  — new: {film_result.new}, "
                f"removed: {film_result.removed}, "
                f"unchanged: {film_result.unchanged}"
            )

        if series_path:
            series_result = reconcile_remote_scan(session, series_results, MediaType.series)
            print(
                f"Series — new: {series_result.new}, "
                f"removed: {series_result.removed}, "
                f"unchanged: {series_result.unchanged}"
            )
