"""Application runner — starts APScheduler with SFTP scan and OMDB enrichment jobs.

Run with:
    python -m file_fetcher.app_runner

The runner:
1. Calls :func:`~file_fetcher.bootstrap.initialize_app` to load env + seed settings.
2. Reads cron expressions from the DB (``sftp_scan_cron``, ``omdb_enrich_cron``).
3. Registers two background jobs and starts the scheduler.
4. Blocks the main thread indefinitely via ``threading.Event().wait()``.
"""

from __future__ import annotations

import logging
from threading import Event

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from file_fetcher.bootstrap import initialize_app
from file_fetcher.db import get_session
from file_fetcher.services import settings_service
from file_fetcher.services.enrichment import run_enrichment_batch
from file_fetcher.services.scanner_service import run_full_scan

log = logging.getLogger(__name__)


# ── Scheduled jobs ─────────────────────────────────────────────────────────────


def scheduled_scan() -> None:
    """SFTP scan job — reads settings at job-start for live config changes."""
    with get_session() as session:
        enabled = settings_service.get(session, "sftp_scan_enabled", "true")
        if enabled.lower() != "true":
            log.info("SFTP scan disabled — skipping scheduled run.")
            return

    try:
        with get_session() as session:
            run_full_scan(session)
    except Exception as exc:
        log.error(f"scheduled_scan: job failed: {exc}", exc_info=True)


def scheduled_enrich() -> None:
    """OMDB enrichment job — reads settings at job-start for live config changes."""
    try:
        with get_session() as session:
            batch_limit = int(settings_service.get(session, "omdb_batch_limit", "50"))
            daily_quota = int(settings_service.get(session, "omdb_daily_quota", "1000"))

        with get_session() as session:
            run_enrichment_batch(session, batch_limit=batch_limit, daily_quota=daily_quota)
    except Exception as exc:
        log.error(f"scheduled_enrich: job failed: {exc}", exc_info=True)


# ── Main runner ────────────────────────────────────────────────────────────────


def main() -> None:
    """Initialise the application and start the scheduler."""
    import logging as _logging

    _logging.basicConfig(
        level=_logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    )

    initialize_app()

    with get_session() as session:
        sftp_scan_cron = settings_service.get(session, "sftp_scan_cron", "0 3 * * *")
        omdb_enrich_cron = settings_service.get(session, "omdb_enrich_cron", "0 4 * * *")

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        scheduled_scan,
        CronTrigger.from_crontab(sftp_scan_cron),
        id="scan",
        max_instances=1,
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_enrich,
        CronTrigger.from_crontab(omdb_enrich_cron),
        id="enrich",
        max_instances=1,
        replace_existing=True,
    )
    scheduler.start()

    log.info(
        "Scheduler started. SFTP scan: %s. Enrichment: %s.",
        sftp_scan_cron,
        omdb_enrich_cron,
    )

    # Block main thread indefinitely — scheduler runs in background threads.
    Event().wait()


if __name__ == "__main__":
    main()