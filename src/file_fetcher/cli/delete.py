"""CLI commands: file-fetcher delete / file-fetcher reset

Covers: Story 3.3
"""

from __future__ import annotations

import logging
import sys

from file_fetcher.db import get_session
from file_fetcher.models.movie import Movie
from file_fetcher.models.show import Show
from file_fetcher.services.catalog import delete_entry, full_reset

log = logging.getLogger(__name__)


def run_delete(movie_id: int | None = None, show_id: int | None = None) -> None:
    """Delete a catalog entry after user confirmation.

    Args:
        movie_id: ID of the movie to delete (mutually exclusive with show_id).
        show_id:  ID of the show to delete.
    """
    if movie_id is None and show_id is None:
        print("Error: provide --movie <id> or --show <id>.", file=sys.stderr)
        sys.exit(1)

    with get_session() as session:
        if movie_id is not None:
            entry = session.get(Movie, movie_id)
            kind = "Movie"
            eid = movie_id
        else:
            entry = session.get(Show, show_id)
            kind = "Show"
            eid = show_id

        if entry is None:
            print(f"Error: {kind} id={eid} not found.", file=sys.stderr)
            sys.exit(1)
            return

        title = entry.title
        answer = input(f"Delete '{title}' and all associated data? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

        delete_entry(session, movie_id=movie_id, show_id=show_id)

    print(f"Deleted {kind} '{title}' (id={eid}).")


def run_reset() -> None:
    """Reset the entire catalog database after strict confirmation."""
    answer = input("Type 'RESET' to confirm: ").strip()
    if answer != "RESET":
        print("Aborted — did not receive 'RESET'.")
        sys.exit(0)
        return

    with get_session() as session:
        full_reset(session)

    print("Database reset complete.")
