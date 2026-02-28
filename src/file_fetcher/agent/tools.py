"""ADK tool factories — wrap existing functionality for the agent.

Each ``make_*`` function returns a plain Python function suitable for passing
to ``google.adk.agents.Agent(tools=[...])``.  The returned functions have
proper type hints and docstrings so ADK can auto-generate the tool schema
for the LLM.

Runtime dependencies (scanner instance, API keys) are captured via closures
so they never leak into the tool signature seen by the model.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

from file_fetcher import logger
from file_fetcher.ratings import get_ratings as _get_ratings

if TYPE_CHECKING:
    from file_fetcher.scanner import SFTPScanner

# ── Security constants (carried over from the old llm/base.py) ────────────
_MAX_QUERY_LENGTH = 500
_MAX_AGE_DAYS_CAP = 365


def sanitize_query(raw: str) -> str:
    """Strip control characters and truncate a user query.

    Removes ASCII/Unicode control chars (C0, C1, DEL) but keeps normal
    whitespace (space, tab, newline).  Truncates to *_MAX_QUERY_LENGTH*.
    """
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", raw)
    return cleaned[:_MAX_QUERY_LENGTH]


# ── Tool factories ────────────────────────────────────────────────────────

def make_search_tool(scanner: "SFTPScanner"):
    """Return an ADK-compatible ``search_sftp_server`` function.

    The *scanner* instance is captured by closure so it is invisible to the
    LLM schema.
    """

    def search_sftp_server(
        media_type: str = "all",
        year: int | None = None,
        max_age_days: int | None = None,
        keywords: list[str] | None = None,
    ) -> dict:
        """Search the SFTP media server for files matching the given filters.

        Use this tool to find movies or TV shows available on the server.

        Args:
            media_type: One of 'movies', 'tv', or 'all'. Defaults to 'all'.
            year: Exact release year to filter by (e.g. 2026). None means any year.
            max_age_days: Only return items uploaded within this many days.
                Use 30 for 'recent', 7 for 'last week', etc. None means no age limit.
            keywords: List of exact strings that must appear in the filename
                (e.g. ['1080p', 'x264']). Do NOT use plot/genre keywords here.
        """
        # Cap max_age_days for safety
        if max_age_days is not None and max_age_days > _MAX_AGE_DAYS_CAP:
            max_age_days = _MAX_AGE_DAYS_CAP

        logger.info(
            "Tool search_sftp_server called: media_type=%s year=%s max_age_days=%s keywords=%s",
            media_type, year, max_age_days, keywords,
        )

        entries = scanner.scan(
            media_type=media_type,
            year=year,
            max_age_days=max_age_days,
            keywords=keywords,
        )

        results = [
            {
                "index": i,
                "title": e.title,
                "year": e.year,
                "remote_path": e.remote_path,
                "modified_date": e.modified_date.strftime("%Y-%m-%d"),
                "size_bytes": e.size_bytes,
                "media_type": e.media_type,
            }
            for i, e in enumerate(entries)
        ]

        return {"status": "success", "count": len(results), "results": results}

    return search_sftp_server


def make_ratings_tool(api_key: str):
    """Return an ADK-compatible ``get_movie_ratings`` function.

    The *api_key* is captured by closure so the LLM never sees it.
    """

    def get_movie_ratings(title: str, year: int | None = None) -> dict:
        """Fetch IMDb, Rotten Tomatoes, and Metacritic ratings for a movie or show.

        Use this tool to retrieve detailed metadata (ratings, genre, plot,
        director, actors) from OMDb for a single title.

        Args:
            title: The name of the movie or TV show.
            year: Optional release year to disambiguate titles.
        """
        logger.info("Tool get_movie_ratings called: title=%s year=%s", title, year)

        ratings = _get_ratings(title, year, api_key)

        return {
            "status": "success",
            "title": title,
            "imdb": ratings.imdb,
            "rotten_tomatoes": ratings.rotten_tomatoes,
            "metacritic": ratings.metacritic,
            "genre": ratings.genre,
            "rated": ratings.rated,
            "runtime": ratings.runtime,
            "plot": ratings.plot,
            "year": ratings.year,
            "director": ratings.director,
            "actors": ratings.actors,
            "language": ratings.language,
            "awards": ratings.awards,
            "type": ratings.type,
        }

    return get_movie_ratings


# ── DB-backed catalog search tool (Story 5.2) ─────────────────────────────

def make_catalog_search_tool():
    """Return an ADK-compatible ``search_catalog_db`` function.

    The tool opens its own DB session so it can be called within the agent's
    invocation context without requiring a session to be passed across tool
    boundaries.
    """

    def search_catalog_db(
        query: str,
        media_type: Optional[str] = None,
    ) -> list[dict]:
        """Search the local media catalog database by title, genre, actor, or director.

        Returns titles with availability status and ratings from the local DB.
        Never scans the SFTP server live.

        Args:
            query: Free-text search term — title, genre keyword, actor name,
                or director name.
            media_type: ``"film"`` for movies only, ``"series"`` for TV shows
                only, or ``None`` / omitted for both.
        """
        logger.info(
            "Tool search_catalog_db called: query=%r media_type=%s",
            query,
            media_type,
        )

        from file_fetcher.db import get_session  # noqa: PLC0415
        from file_fetcher.services.catalog import search_catalog  # noqa: PLC0415

        try:
            with get_session() as session:
                results = search_catalog(session, query, media_type=media_type, limit=50)

            return [
                {
                    "title": r.title,
                    "year": r.year,
                    "media_type": r.media_type,
                    "availability": r.availability,
                    "imdb_rating": r.imdb_rating,
                    "genre": r.genre,
                }
                for r in results
            ]
        except Exception as exc:  # noqa: BLE001
            logger.error("search_catalog_db failed: %s", exc)
            return []

    return search_catalog_db
