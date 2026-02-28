"""Unit tests for settings_service (Story 6.1)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from file_fetcher.models.base import Base
from file_fetcher.models.setting import Setting
from file_fetcher.services import settings_service


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


# ── get() ────────────────────────────────────────────────────────────────────


class TestGet:
    def test_get_existing_returns_value(self, db_session: Session) -> None:
        db_session.add(Setting(key="foo", value="bar"))
        db_session.flush()
        assert settings_service.get(db_session, "foo") == "bar"

    def test_get_missing_returns_none_default(self, db_session: Session) -> None:
        result = settings_service.get(db_session, "nonexistent")
        assert result is None

    def test_get_missing_returns_custom_default(self, db_session: Session) -> None:
        result = settings_service.get(db_session, "nonexistent", default="my_default")
        assert result == "my_default"

    def test_get_nullable_value_returns_none(self, db_session: Session) -> None:
        db_session.add(Setting(key="nullable_key", value=None))
        db_session.flush()
        result = settings_service.get(db_session, "nullable_key", default="fallback")
        # The row exists but value is None — returns None (not fallback)
        assert result is None


# ── set() ────────────────────────────────────────────────────────────────────


class TestSet:
    def test_set_new_key_creates_setting(self, db_session: Session) -> None:
        row = settings_service.set(db_session, "new_key", "new_value")
        assert row.key == "new_key"
        assert row.value == "new_value"
        assert row.id is not None

    def test_set_existing_key_updates_value(self, db_session: Session) -> None:
        db_session.add(Setting(key="existing", value="old"))
        db_session.flush()

        row = settings_service.set(db_session, "existing", "updated")
        assert row.value == "updated"

        # Confirm only one row for this key
        count = db_session.query(Setting).filter_by(key="existing").count()
        assert count == 1

    def test_set_returns_setting_instance(self, db_session: Session) -> None:
        result = settings_service.set(db_session, "k", "v")
        assert isinstance(result, Setting)


# ── seed_defaults() ───────────────────────────────────────────────────────────


class TestSeedDefaults:
    def test_seed_inserts_all_defaults_on_empty_db(self, db_session: Session) -> None:
        settings_service.seed_defaults(db_session)
        db_session.flush()
        keys = {row.key for row in db_session.query(Setting).all()}
        assert keys == set(settings_service.DEFAULTS.keys())

    def test_seed_idempotent_does_not_duplicate(self, db_session: Session) -> None:
        settings_service.seed_defaults(db_session)
        db_session.flush()
        settings_service.seed_defaults(db_session)
        db_session.flush()
        count = db_session.query(Setting).count()
        assert count == len(settings_service.DEFAULTS)

    def test_seed_does_not_overwrite_existing_value(self, db_session: Session) -> None:
        # Pre-seed with a custom value
        db_session.add(Setting(key="sftp_scan_enabled", value="false"))
        db_session.flush()

        settings_service.seed_defaults(db_session)
        db_session.flush()

        value = settings_service.get(db_session, "sftp_scan_enabled")
        assert value == "false"  # unchanged — not overwritten by seed

    def test_seed_inserts_remaining_missing_keys(self, db_session: Session) -> None:
        # Only pre-populate one key
        db_session.add(Setting(key="sftp_scan_enabled", value="false"))
        db_session.flush()

        settings_service.seed_defaults(db_session)
        db_session.flush()

        # All keys should now exist
        all_keys = {row.key for row in db_session.query(Setting).all()}
        assert set(settings_service.DEFAULTS.keys()).issubset(all_keys)

    def test_seed_defaults_keys_match_expected(self, db_session: Session) -> None:
        expected_keys = {
            # SFTP
            "sftp_host",
            "sftp_port",
            "sftp_user",
            "sftp_password",
            "sftp_remote_path",
            "sftp_scan_enabled",
            "sftp_scan_cron",
            # OMDB
            "omdb_api_key",
            "omdb_enrich_cron",
            "omdb_batch_limit",
            "omdb_daily_quota",
            # Downloads
            "download_dir",
            "scheduler_poll_interval",
            # Web
            "web_poll_interval_seconds",
        }
        assert set(settings_service.DEFAULTS.keys()) == expected_keys


# ── get_all() ────────────────────────────────────────────────────────────────


class TestGetAll:
    def test_get_all_returns_all_settings_ordered(self, db_session: Session) -> None:
        db_session.add_all([
            Setting(key="z_key", value="z"),
            Setting(key="a_key", value="a"),
            Setting(key="m_key", value="m"),
        ])
        db_session.flush()

        rows = settings_service.get_all(db_session)
        assert len(rows) == 3
        keys = [r.key for r in rows]
        assert keys == sorted(keys)

    def test_get_all_empty_db(self, db_session: Session) -> None:
        rows = settings_service.get_all(db_session)
        assert rows == []
