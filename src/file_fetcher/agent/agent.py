"""ADK agent definition and programmatic runner."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from file_fetcher import logger
from file_fetcher.agent.tools import make_search_tool, make_ratings_tool, make_catalog_search_tool, sanitize_query

if TYPE_CHECKING:
    from file_fetcher.scanner import SFTPScanner

# ── System instruction (DB-backed catalog agent — Story 5.2) ─────────────

_CATALOG_SYSTEM_INSTRUCTION = """\
You are a media catalog assistant. Search the local database catalog using
the `search_catalog_db` tool. Never scan the SFTP server live.

## Workflow

1. **Parse the user's request** — identify media type, year, genre, actor,
   or director keywords.
2. **Call `search_catalog_db`** with the query and optional media_type filter.
   Only use media_type if the user explicitly asked for films or series.
3. **Semantically filter** the results — if the user expressed thematic
   preferences, keep only items whose genre, plot, or metadata match.
4. **Return your final answer as a JSON array** with exactly this schema:

```json
[
  {
    "title": "Movie A",
    "year": 2010,
    "media_type": "film",
    "availability": "remote_only",
    "imdb_rating": "8.5",
    "genre": "Sci-Fi"
  }
]
```

Return **only** valid JSON — no markdown fences, no extra text.
If no results match, return an empty array: `[]`.
"""

# ── Legacy system instruction (SFTP-based agent — preserved for backward compat) ─

_SYSTEM_INSTRUCTION = """\
You are an intelligent media search assistant for a personal SFTP media server.

Your job is to help the user find movies or TV shows on the server and present
them with detailed metadata so they can decide what to download.

## Workflow

1. **Parse the user's request** — identify media type, year, recency, filename
   keywords, and any semantic/thematic criteria (genre, plot, actors, etc.).
2. **Call `search_sftp_server`** with the appropriate hard filters (media_type,
   year, max_age_days, keywords). Only use filters that the user explicitly
   mentioned. If the user didn't specify a year, don't pass one.
3. **For each result**, call `get_movie_ratings` to fetch metadata (ratings,
   plot, genre, actors, director). If there are more than 30 results, only
   fetch ratings for the first 30 to avoid excessive API calls.
4. **Semantically filter** the enriched results — if the user expressed
   thematic preferences (e.g. "sci-fi", "like Game of Thrones", "comedy"),
   keep only items whose genre, plot, or metadata match those preferences.
5. **Return your final answer as a JSON object** with exactly this schema:

```json
{
  "selected": [
    {"index": 0, "title": "Movie A", "reason": "Matches sci-fi criteria"},
    {"index": 3, "title": "Movie D", "reason": "Space adventure plot"}
  ]
}
```

The `index` field must match the index returned by `search_sftp_server`.
The `reason` field is a short explanation of why you selected this item.

## Important Rules

- Always call `search_sftp_server` first. Never guess what's on the server.
- Always return valid JSON as your final answer — no markdown fences, no
  extra text before or after the JSON.
- If no results match after filtering, return `{"selected": []}`.
- Prefer quality over quantity: only include genuinely relevant results.
"""


def create_catalog_agent(model: str = "gemini-2.5-flash") -> Any:
    """Build the FileFetcher ADK agent backed by the local DB catalog.

    Uses ``search_catalog_db`` tool — no live SFTP scanning.
    """
    from google.adk.agents import Agent  # lazy — avoids loading google.genai at import time

    catalog_tool = make_catalog_search_tool()

    agent = Agent(
        name="file_fetcher_catalog_agent",
        model=model,
        description="Searches the local media catalog database.",
        instruction=_CATALOG_SYSTEM_INSTRUCTION,
        tools=[catalog_tool],
    )
    return agent


def create_agent(
    scanner: "SFTPScanner",
    omdb_api_key: str,
    model: str = "gemini-2.5-flash",
) -> Any:
    """Build the FileFetcher ADK agent with tools bound to *scanner*.

    .. deprecated::
        Prefer :func:`create_catalog_agent` for DB-backed search (Story 5.2).
        This function is retained for the legacy SFTP-scan flow.
    """
    from google.adk.agents import Agent  # lazy — avoids loading google.genai at import time

    search_tool = make_search_tool(scanner)
    ratings_tool = make_ratings_tool(omdb_api_key)

    agent = Agent(
        name="file_fetcher_agent",
        model=model,
        description="Searches an SFTP media server and retrieves ratings.",
        instruction=_SYSTEM_INSTRUCTION,
        tools=[search_tool, ratings_tool],
    )
    return agent


async def _run_agent_async(agent: Any, query: str) -> str:
    """Send *query* to the agent and collect the final text response."""
    from google.adk.runners import Runner  # lazy
    from google.adk.sessions import InMemorySessionService  # lazy
    from google.genai import types  # lazy

    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name="file_fetcher",
        session_service=session_service,
    )

    session = await session_service.create_session(
        app_name="file_fetcher",
        user_id="cli_user",
    )

    safe_query = sanitize_query(query)
    user_message = types.Content(
        role="user",
        parts=[types.Part(text=safe_query)],
    )

    logger.info("Sending query to ADK agent: %s", safe_query)

    final_text = ""
    try:
        async for event in runner.run_async(
            session_id=session.id,
            user_id="cli_user",
            new_message=user_message,
        ):
            # Collect only the agent's final text parts
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text and not event.partial:
                        final_text = part.text  # keep overwriting — last non-partial wins
    except Exception as exc:  # noqa: BLE001
        logger.error("ADK agent run failed: %s", exc)
        return '{"error": "AI search unavailable. Please try a direct search."}'

    logger.info("Agent final response length: %d chars", len(final_text))
    return final_text


def run_agent(agent: Any, query: str) -> list[dict]:
    """Run the agent synchronously and return the selected items.

    Returns a list of dicts, each with keys ``index``, ``title``, ``reason``.
    Returns an empty list on error or if no results matched.
    """
    raw = asyncio.run(_run_agent_async(agent, query))

    # Strip markdown code fences if the model wrapped the JSON
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    # Handle graceful API error response
    if '"error"' in cleaned:
        logger.warning("Agent returned error response: %s", cleaned[:200])
        return []

    try:
        data = json.loads(cleaned)
        selected = data.get("selected", [])
        if not isinstance(selected, list):
            logger.warning("Agent returned non-list 'selected': %s", type(selected))
            return []
        return selected
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error("Failed to parse agent response as JSON: %s — raw: %s", exc, raw[:500])
        print(f"⚠️  Could not parse agent response. Raw output:\n{raw[:500]}")
        return []


def run_catalog_agent(agent: Any, query: str) -> list[dict]:
    """Run the catalog agent synchronously and return the JSON array of results.

    Returns a list of dicts with keys: ``title``, ``year``, ``media_type``,
    ``availability``, ``imdb_rating``, ``genre``.
    Returns an empty list on error or if no results matched.
    """
    raw = asyncio.run(_run_agent_async(agent, query))

    # Handle graceful API error response
    if not raw or '"error"' in raw:
        logger.warning("Catalog agent returned error or empty response.")
        return []

    # Strip markdown code fences if the model wrapped the JSON
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
        # Some models may wrap in an object key
        if isinstance(data, dict):
            for key in ("results", "selected", "items"):
                if key in data and isinstance(data[key], list):
                    return data[key]
        logger.warning("Catalog agent returned unexpected JSON shape: %s", type(data))
        return []
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(
            "Failed to parse catalog agent response: %s — raw: %s", exc, raw[:500]
        )
        return []

