"""Watcher runner — entry point for ``python -m file_fetcher.watcher_runner``.

Starts watchdog observers for both the local films and series directories,
then blocks until terminated.

Covers: Story 3.2
"""

from __future__ import annotations

import logging
import os
import signal
from threading import Event

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


def main() -> None:
    """Start filesystem observers and block until SIGTERM/SIGINT."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    films_path = os.environ.get("LOCAL_FILMS_PATH", "/data/films")
    series_path = os.environ.get("LOCAL_SERIES_PATH", "/data/series")

    log.info("Watching films: %s, series: %s", films_path, series_path)

    from watchdog.observers import Observer  # type: ignore

    from file_fetcher.db import SessionLocal
    from file_fetcher.models.enums import MediaType
    from file_fetcher.services.watcher_service import MediaFileEventHandler

    films_handler = MediaFileEventHandler(
        session_factory=SessionLocal,
        media_type=MediaType.film,
        source_directory=films_path,
    )
    series_handler = MediaFileEventHandler(
        session_factory=SessionLocal,
        media_type=MediaType.series,
        source_directory=series_path,
    )

    observer = Observer()
    observer.schedule(films_handler, films_path, recursive=False)
    observer.schedule(series_handler, series_path, recursive=False)
    observer.start()
    log.info("Observers started.")

    stop_event = Event()

    def _shutdown(signum, frame) -> None:  # pragma: no cover
        log.info("Received signal %s — shutting down watcher.", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        stop_event.wait()
    finally:
        observer.stop()
        observer.join()
        log.info("Watcher stopped.")


if __name__ == "__main__":
    main()
