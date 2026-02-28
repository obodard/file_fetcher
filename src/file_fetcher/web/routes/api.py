"""API routes for file_fetcher web layer."""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, Response

from file_fetcher.db import get_session
from file_fetcher.models.omdb_data import OmdbData
from file_fetcher.services.catalog import get_by_id, search_catalog
from file_fetcher.services.queue_service import AlreadyQueuedError, enqueue_catalog_entry
from file_fetcher.web.utils import make_toast

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 300" width="200" height="300">'
    '<rect width="200" height="300" fill="#2a2a2a"/>'
    '<text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle"'
    ' fill="#555" font-size="14" font-family="sans-serif">No poster</text>'
    "</svg>"
)

_MEDIA_TYPE_MAP = {
    "movie": "film",
    "series": "series",
}


@router.get("/posters/{catalog_id}")
async def get_poster(catalog_id: int) -> Response:
    """Return poster image bytes for a catalog entry.

    Tries movie_id first, then show_id.  Falls back to an inline SVG placeholder
    if no poster blob is stored for the entry.
    """
    with get_session() as session:
        omdb = (
            session.query(OmdbData)
            .filter(
                (OmdbData.movie_id == catalog_id) | (OmdbData.show_id == catalog_id)
            )
            .first()
        )

        if omdb and omdb.poster_blob:
            content_type = omdb.poster_content_type or "image/jpeg"
            return Response(content=omdb.poster_blob, media_type=content_type)

    # Return SVG placeholder
    return Response(content=_PLACEHOLDER_SVG, media_type="image/svg+xml")


@router.get("/grid")
async def grid_fragment(
    request: Request,
    q: str = Query(default=""),
    type: Optional[str] = Query(default=None),
    genre: Optional[str] = Query(default=None),
    year_min: Optional[int] = Query(default=None),
    year_max: Optional[int] = Query(default=None),
    min_rating: Optional[float] = Query(default=None),
    availability: Optional[str] = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=40, ge=1, le=100),
    ai: int = Query(default=0),
) -> HTMLResponse:
    """Return an HTML fragment (no base layout) of grid rows for HTMX infinite scroll.

    - Normal mode: delegates to ``search_catalog``; additional filters applied in-process.
    - AI mode (``ai=1``): delegates to the Gemini catalog agent, then looks up results in DB.
    """
    templates = request.app.state.templates
    media_type = _MEDIA_TYPE_MAP.get(type or "", None)

    entries = []

    if ai:
        # ── AI search path ────────────────────────────────────────────────
        gemini_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not gemini_key:
            log.warning("AI search requested but no GOOGLE_API_KEY configured")
            return HTMLResponse(
                content='<div class="alert alert-warning" role="alert">'
                        'AI search is not configured. Please set GOOGLE_API_KEY in your environment.'
                        "</div>",
                status_code=200,
            )
        try:
            from file_fetcher.agent.agent import create_catalog_agent, run_catalog_agent  # lazy

            agent = create_catalog_agent()
            ai_results = run_catalog_agent(agent, q)

            # Look up each AI result in DB to get full CatalogResult (with id, poster, etc.)
            with get_session() as session:
                for item in ai_results:
                    title = item.get("title", "")
                    catalog_results = search_catalog(session, query=title, limit=5)
                    for cr in catalog_results:
                        if cr.title.lower() == title.lower():
                            entries.append(cr)
                            break
                    else:
                        # Title not found exactly — skip
                        pass
        except Exception as exc:  # noqa: BLE001
            log.error("AI search failed: %s", exc)
            return HTMLResponse(
                content='<div class="alert alert-error" role="alert">AI search failed. Please try again.</div>',
                status_code=200,
            )
    else:
        # ── Standard search path ──────────────────────────────────────────
        with get_session() as session:
            raw = search_catalog(
                session,
                query=q,
                media_type=media_type,
                limit=limit + offset,  # fetch enough to slice at offset
            )

        # Slice at offset
        raw = raw[offset : offset + limit]

        # Post-filter by additional params
        filtered = []
        for entry in raw:
            if genre and entry.genre and genre.lower() not in entry.genre.lower():
                continue
            if year_min and entry.year and entry.year < year_min:
                continue
            if year_max and entry.year and entry.year > year_max:
                continue
            if min_rating and entry.imdb_rating:
                try:
                    if float(entry.imdb_rating) < min_rating:
                        continue
                except ValueError:
                    pass
            if availability:
                if availability == "local" and entry.availability not in ("in_collection", "both"):
                    continue
                if availability == "queued" and entry.availability != "remote_only_downloading":
                    continue
            filtered.append(entry)

        entries = filtered

    return templates.TemplateResponse(
        request,
        "partials/grid_rows.html",
        {
            "entries": entries,
            "offset": offset,
            "limit": limit,
            "next_offset": offset + limit,
            "q": q,
            "type": type or "",
            "genre": genre or "",
            "year_min": year_min or "",
            "year_max": year_max or "",
            "min_rating": min_rating or "",
            "availability": availability or "",
            "ai": ai,
        },
    )


# ── Story 8.2 — queue action endpoints ────────────────────────────────────────

def _action_buttons_response(
    request: Request,
    catalog_id: int,
    *,
    toast_message: str,
    toast_type: str,
) -> HTMLResponse:
    """Re-fetch entry state, render action_buttons partial + toast OOB."""
    templates = request.app.state.templates

    with get_session() as session:
        entry = get_by_id(session, catalog_id)

    if entry is None:
        return HTMLResponse(
            content=make_toast("Entry not found.", "error"),
            status_code=404,
        )

    partial_html = templates.get_template("partials/action_buttons.html").render(
        {"entry": entry, "request": request}
    )
    return HTMLResponse(content=partial_html + make_toast(toast_message, toast_type))


@router.post("/queue/add", response_class=HTMLResponse)
async def queue_add(
    request: Request,
    catalog_id: int = Form(...),
) -> HTMLResponse:
    """Add a catalog entry to the download queue via HTMX form post.

    Returns an updated action-buttons partial with a toast OOB fragment.
    Returns 409 with error toast if the entry is already queued.
    """
    try:
        with get_session() as session:
            enqueue_catalog_entry(session, catalog_id)
    except AlreadyQueuedError:
        return HTMLResponse(
            content=make_toast("Already in queue.", "error"),
            status_code=409,
        )
    except ValueError as exc:
        return HTMLResponse(
            content=make_toast(str(exc), "error"),
            status_code=422,
        )

    return _action_buttons_response(
        request,
        catalog_id,
        toast_message="Added to queue!",
        toast_type="success",
    )


@router.post("/queue/download-now", response_class=HTMLResponse)
async def queue_download_now(
    request: Request,
    catalog_id: int = Form(...),
) -> HTMLResponse:
    """Add a catalog entry to the queue with maximum priority (download now).

    Same response contract as ``/api/queue/add``.
    """
    try:
        with get_session() as session:
            enqueue_catalog_entry(session, catalog_id, priority=999)
    except AlreadyQueuedError:
        return HTMLResponse(
            content=make_toast("Already in queue.", "error"),
            status_code=409,
        )
    except ValueError as exc:
        return HTMLResponse(
            content=make_toast(str(exc), "error"),
            status_code=422,
        )

    return _action_buttons_response(
        request,
        catalog_id,
        toast_message="Download started!",
        toast_type="success",
    )
