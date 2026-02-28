"""Application bootstrap sequence.

Call :func:`initialize_app` once at the start of every CLI command,
the scheduler runner, and the web application factory to ensure:

1. ``.env`` is loaded into the environment.
2. A DB session is obtained.
3. Default settings are seeded (idempotent — existing values are never overwritten).
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv

log = logging.getLogger(__name__)


def initialize_app() -> None:
    """Run the full application bootstrap sequence.

    Safe to call multiple times — :func:`~file_fetcher.services.settings_service.seed_defaults`
    is idempotent.
    """
    load_dotenv()

    from file_fetcher.db import get_session
    from file_fetcher.services import settings_service

    with get_session() as session:
        settings_service.seed_defaults(session)

    log.debug("bootstrap.initialize_app: complete.")
