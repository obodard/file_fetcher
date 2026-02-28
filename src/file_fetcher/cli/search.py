"""CLI command: file-fetcher search

Searches the local catalog by title, genre, actor, or director.
Optionally uses the Gemini ADK agent for natural-language interpretation.

Examples:
  file-fetcher search "sci-fi from the 80s"
  file-fetcher search "Tom Hanks" --films
  file-fetcher search "drama" --series --limit 10
  file-fetcher search "Matrix" --no-ai
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Optional

import click
from tabulate import tabulate

from file_fetcher.db import get_session
from file_fetcher.services.catalog import search_catalog

log = logging.getLogger(__name__)

_TABLE_FORMAT = "simple"
_DEFAULT_LIMIT = 20


def _derive_media_type(films: bool, series: bool) -> Optional[str]:
    if films:
        return "film"
    if series:
        return "series"
    return None


def _results_to_rows(results: list) -> list[list]:
    """Convert CatalogResult list to tabulate-ready rows."""
    rows = []
    for r in results:
        genre_display = (r.genre or "N/A").split(",")[0].strip() if r.genre else "N/A"
        rows.append(
            [
                r.title,
                r.year if r.year is not None else "N/A",
                r.media_type,
                r.availability,
                r.imdb_rating or "N/A",
                genre_display,
            ]
        )
    return rows


def _display_results(results: list) -> None:
    headers = ["Title", "Year", "Type", "Availability", "IMDb Rating", "Genre"]
    rows = _results_to_rows(results)
    click.echo(tabulate(rows, headers=headers, tablefmt=_TABLE_FORMAT))


def _run_with_ai(
    query: str,
    media_type: Optional[str],
    limit: int,
) -> list:
    """Attempt to get results via the Gemini ADK catalog agent.

    Falls back to an empty list on any failure (caller handles fallback).
    """
    google_api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not google_api_key:
        log.debug("GOOGLE_API_KEY not set — skipping AI search")
        return []

    try:
        from file_fetcher.agent import create_catalog_agent, run_catalog_agent  # noqa: PLC0415
        from file_fetcher.config import load_search_config  # noqa: PLC0415

        search_cfg = load_search_config()
        os.environ.setdefault("GOOGLE_API_KEY", search_cfg.google_api_key)

        agent = create_catalog_agent(model=search_cfg.gemini_model)
        ai_results = run_catalog_agent(agent, query)
        if ai_results:
            # ai_results are dicts — map back to CatalogResult for display consistency
            # For simplicity, run direct search and use that for tabular display
            # (AI provides semantic ranking; direct DB search provides structure)
            pass
        return ai_results
    except Exception as exc:  # noqa: BLE001
        log.warning("AI search failed, falling back to direct search: %s", exc)
        return []


@click.command()
@click.argument("query")
@click.option("--films", is_flag=True, default=False, help="Show films only.")
@click.option("--series", is_flag=True, default=False, help="Show series only.")
@click.option(
    "--limit",
    default=_DEFAULT_LIMIT,
    show_default=True,
    type=int,
    help="Maximum number of results to return.",
)
@click.option(
    "--no-ai",
    is_flag=True,
    default=False,
    help="Bypass Gemini AI — use direct keyword search only.",
)
def search(query: str, films: bool, series: bool, limit: int, no_ai: bool) -> None:
    """Search the catalog by title, genre, actor, or director.

    QUERY: Free-text search term (title keyword, genre, actor, director).
    """
    media_type = _derive_media_type(films, series)

    ai_results: list = []

    # ── AI path ────────────────────────────────────────────────────────────
    if not no_ai:
        try:
            ai_results = _run_with_ai(query, media_type, limit)
        except Exception:  # noqa: BLE001
            log.warning("AI search failed unexpectedly, using direct search.")
            ai_results = []

    # ── Direct DB path (always used for tabular display) ───────────────────
    try:
        with get_session() as session:
            db_results = search_catalog(session, query, media_type=media_type, limit=limit)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"⚠️  Database error: {exc}", err=True)
        sys.exit(1)

    # Prefer AI-ranked titles for display order when AI returned results
    if ai_results and db_results:
        # Build a lookup by title for re-ordering
        db_by_title = {r.title.lower(): r for r in db_results}
        ordered: list = []
        seen: set = set()
        for ai_item in ai_results:
            ai_title = (ai_item.get("title") or "").lower()
            if ai_title in db_by_title and ai_title not in seen:
                ordered.append(db_by_title[ai_title])
                seen.add(ai_title)
        # Append any non-AI-selected DB results at the end
        for r in db_results:
            if r.title.lower() not in seen:
                ordered.append(r)
        display_results = ordered[:limit]
    else:
        display_results = db_results

    if not display_results:
        click.echo(f"No titles found matching '{query}'.")
        return

    _display_results(display_results)
