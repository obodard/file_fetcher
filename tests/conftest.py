"""Shared test fixtures — in-memory SQLite DB for model tests."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from file_fetcher.models.base import Base


@pytest.fixture(scope="function")
def db_session():
    """Yield a fresh in-memory SQLite session, then tear down."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()
