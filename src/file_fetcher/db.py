"""Database engine and session factory.

Provides:
- ``engine``: SQLAlchemy Engine created from DATABASE_URL
- ``SessionLocal``: sessionmaker bound to engine
- ``get_session()``: context manager yielding a Session (commit on success, rollback on exception)
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

log = logging.getLogger(__name__)

_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///:memory:")

engine = create_engine(
    _DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy Session, committing on success and rolling back on exception."""
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
