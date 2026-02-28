"""CLI command: file-fetcher override

Sets title_override / year_override on a catalog entry so re-enrichment
uses the corrected title.

Covers:
  - Story 2.4: movie override (positional movie_id)
  - Story 2.5: show override (--show flag)
"""

from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv

from file_fetcher.db import get_session

log = logging.getLogger(__name__)


def run_override(
    movie_id: int | None = None,
    show_id: int | None = None,
    title: str | None = None,
    year: int | None = None,
) -> None:
    """Entry point for the ``file-fetcher override`` command.

    Args:
        movie_id: Movie PK to override (mutually exclusive with show_id).
        show_id:  Show PK to override (mutually exclusive with movie_id).
        title:    New title override value (None = leave unchanged).
        year:     New year override value (None = leave unchanged).
    """
    load_dotenv()

    if movie_id is None and show_id is None:
        print("Error: provide a movie_id or --show <show_id>.", file=sys.stderr)
        sys.exit(1)
    if title is None and year is None:
        print("Error: provide --title and/or --year.", file=sys.stderr)
        sys.exit(1)

    with get_session() as session:
        if movie_id is not None:
            from file_fetcher.models.movie import Movie

            movie = session.get(Movie, movie_id)
            if movie is None:
                print(f"Error: Movie id={movie_id} not found.", file=sys.stderr)
                sys.exit(1)
            if title is not None:
                movie.title_override = title
            if year is not None:
                movie.year_override = year
            session.flush()
            print(
                f"✅ Movie id={movie_id} ({movie.title!r}) override set: "
                f"title={movie.title_override!r}, year={movie.year_override}"
            )

        elif show_id is not None:
            from file_fetcher.models.show import Show

            show = session.get(Show, show_id)
            if show is None:
                print(f"Error: Show id={show_id} not found.", file=sys.stderr)
                sys.exit(1)
            if title is not None:
                show.title_override = title
            if year is not None:
                show.year_override = year
            session.flush()
            print(
                f"✅ Show id={show_id} ({show.title!r}) override set: "
                f"title={show.title_override!r}, year={show.year_override}"
            )
