"""Settings service — DB-backed runtime configuration.

Provides:
- ``get(session, key, default=None)``: read a setting value
- ``set(session, key, value)``: upsert a setting value
- ``get_all(session)``: return all Setting rows
- ``seed_defaults(session)``: insert default values without overwriting existing
"""

from __future__ import annotations

import logging
import os

from sqlalchemy.orm import Session

from file_fetcher.models.setting import Setting

log = logging.getLogger(__name__)

# Default settings seeded at every app startup.
DEFAULTS: dict[str, tuple[str, str]] = {
    # key: (default_value, description)
    "sftp_scan_enabled": (
        "true",
        "Enable or disable scheduled SFTP scanning (true/false).",
    ),
    "sftp_scan_cron": (
        "0 3 * * *",
        "Cron expression for SFTP scan schedule (default: 03:00 daily).",
    ),
    "omdb_enrich_cron": (
        "0 4 * * *",
        "Cron expression for OMDB enrichment schedule (default: 04:00 daily).",
    ),
    "omdb_batch_limit": (
        "50",
        "Maximum number of titles to enrich per scheduled batch.",
    ),
    "omdb_daily_quota": (
        "1000",
        "Maximum OMDB API calls allowed per day.",
    ),
    "download_dir": (
        os.environ.get("DOWNLOAD_DIR", "/downloads"),
        "Destination directory for downloaded files.",
    ),
    "scheduler_poll_interval": (
        "60",
        "Scheduler internal polling interval in seconds.",
    ),
}


def get(session: Session, key: str, default: str | None = None) -> str | None:
    """Return the value for *key*, or *default* if not found.

    Args:
        session: Active SQLAlchemy session.
        key:     Setting key.
        default: Fallback value when key does not exist.

    Returns:
        The stored value string, or *default*.
    """
    row: Setting | None = session.query(Setting).filter_by(key=key).first()
    if row is None:
        return default
    return row.value


def set(session: Session, key: str, value: str) -> Setting:  # noqa: A001
    """Upsert a setting and return the updated ``Setting`` row.

    Uses MariaDB / SQLite compatible upsert via SQLAlchemy merge semantics:
    loads existing row by key if present, else creates a new one.

    Args:
        session: Active SQLAlchemy session (caller commits or context-manager commits).
        key:     Setting key.
        value:   New value to store.

    Returns:
        The updated :class:`Setting` instance.
    """
    row: Setting | None = session.query(Setting).filter_by(key=key).first()
    if row is None:
        row = Setting(key=key, value=value)
        session.add(row)
    else:
        row.value = value
    session.flush()
    return row


def get_all(session: Session) -> list[Setting]:
    """Return all :class:`Setting` rows ordered by key.

    Args:
        session: Active SQLAlchemy session.

    Returns:
        List of :class:`Setting` instances.
    """
    return session.query(Setting).order_by(Setting.key).all()


def seed_defaults(session: Session) -> None:
    """Insert default settings that are not already present in the DB.

    This function is idempotent — it NEVER overwrites existing values so that
    user configuration changes are preserved across restarts.

    Args:
        session: Active SQLAlchemy session.
    """
    existing_keys: set[str] = {
        row.key for row in session.query(Setting.key).all()
    }
    inserted = 0
    for key, (default_value, description) in DEFAULTS.items():
        if key not in existing_keys:
            session.add(Setting(key=key, value=default_value, description=description))
            inserted += 1

    if inserted:
        session.flush()
        log.debug("settings_service.seed_defaults: inserted %d default setting(s).", inserted)
    else:
        log.debug("settings_service.seed_defaults: all defaults already present.")
