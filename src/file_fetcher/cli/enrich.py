"""CLI command: file-fetcher enrich

Runs the OMDB enrichment pipeline, processing pending/failed catalog entries.

Covers:
  - Story 2.2: batch enrichment with progress + summary
  - Story 2.4: --id flag for single-entry re-enrichment
  - Story 2.5: combined movie + show progress/summary
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

from file_fetcher.db import get_session
from file_fetcher.services.catalog import get_not_found
from file_fetcher.services.enrichment import enrich_single, enrich_single_show, run_enrichment_batch

log = logging.getLogger(__name__)


def run_enrich(movie_id: int | None = None, show_id: int | None = None) -> None:
    """Entry point for the ``file-fetcher enrich`` command.

    Args:
        movie_id: If provided, enrich only this movie (force=True).
        show_id:  If provided, enrich only this show (force=True).
    """
    load_dotenv()

    batch_limit = int(os.environ.get("OMDB_BATCH_LIMIT", "50"))
    daily_quota = int(os.environ.get("OMDB_DAILY_QUOTA", "900"))

    with get_session() as session:
        if movie_id is not None:
            print(f"Enriching movie id={movie_id} (force=True)...")
            result = enrich_single(session, movie_id, force=True)
            if result is None:
                from file_fetcher.models.movie import Movie

                movie = session.get(Movie, movie_id)
                status = movie.omdb_status.value if movie else "unknown"
                print(f"Status: {status}")
            else:
                print(f"Status: enriched — {result.title} ({result.year})")
            return

        if show_id is not None:
            print(f"Enriching show id={show_id} (force=True)...")
            result = enrich_single_show(session, show_id, force=True)
            if result is None:
                from file_fetcher.models.show import Show

                show = session.get(Show, show_id)
                status = show.omdb_status.value if show else "unknown"
                print(f"Status: {status}")
            else:
                print(f"Status: enriched — {result.title} ({result.year})")
            return

        print(f"Enriching... (batch_limit={batch_limit}, daily_quota={daily_quota})")
        stats = run_enrichment_batch(session, batch_limit=batch_limit, daily_quota=daily_quota)

    # Summary output
    print()
    print(
        f"Movies: {stats['movies_enriched']} enriched, "
        f"{stats['movies_not_found']} not_found, "
        f"{stats['movies_failed']} failed."
    )
    print(
        f"Shows:  {stats['shows_enriched']} enriched, "
        f"{stats['shows_not_found']} not_found, "
        f"{stats['shows_failed']} failed."
    )
    if stats["quota_hit"]:
        print(
            f"⚠️  Daily OMDB quota reached ({stats['requests_made']}/{daily_quota})."
            " Remaining entries stay pending."
        )


def run_not_found() -> None:
    """Entry point for the ``file-fetcher not-found`` command.

    Prints a tabular report of all catalog entries OMDB could not match.
    """
    load_dotenv()

    with get_session() as session:
        entries = get_not_found(session)

    if not entries:
        print("No not_found entries in catalog.")
        return

    # Tabular output
    col_id = max(len("ID"), max(len(str(e.id)) for e in entries))
    col_kind = max(len("Type"), max(len(e.media_kind) for e in entries))
    col_title = max(len("Title"), max(len(e.title) for e in entries))
    col_year = max(len("Year"), max(len(str(e.year or "")) for e in entries))

    header = (
        f"{'ID':<{col_id}}  {'Type':<{col_kind}}  {'Title':<{col_title}}  {'Year':<{col_year}}  Remote Path"
    )
    sep = "-" * (len(header) + 40)
    print(header)
    print(sep)

    for entry in entries:
        paths = entry.remote_paths or ["(no remote files)"]
        for i, path in enumerate(paths):
            if i == 0:
                print(
                    f"{entry.id:<{col_id}}  {entry.media_kind:<{col_kind}}  "
                    f"{entry.title:<{col_title}}  {str(entry.year or ''):<{col_year}}  {path}"
                )
            else:
                print(f"{'':>{col_id + col_kind + col_title + col_year + 8}}  {path}")
