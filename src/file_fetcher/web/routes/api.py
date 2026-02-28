"""API routes for file_fetcher web layer."""
from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, Response

from file_fetcher.db import get_session
from file_fetcher.models.download_queue import DownloadQueue
from file_fetcher.models.enums import DownloadStatus
from file_fetcher.models.omdb_data import OmdbData
from file_fetcher.services.catalog import delete_catalog_entry, full_reset, get_by_id, search_catalog, set_override
from file_fetcher.services.enrichment import enrich_one
from file_fetcher.services.queue_service import AlreadyQueuedError, enqueue_catalog_entry, remove_from_queue, retry_entry
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


# ── Story 9.1 — per-queue-item actions ────────────────────────────────────────


def _render_queue_row_partial(request: Request, queue_id: int) -> str:
    """Render a single queue row partial for OOB HTMX swap."""
    from file_fetcher.web.routes.queue import _fetch_queue_rows  # avoid circular import at module level

    # Refetch entries to get fresh state of the target row
    entries = _fetch_queue_rows()
    matching = [e for e in entries if e.id == queue_id]
    if not matching:
        return ""  # row deleted — return empty

    templates = request.app.state.templates
    html = templates.get_template("partials/queue_row.html").render(
        {"item": matching[0], "request": request}
    )
    # Inject hx-swap-oob so HTMX replaces the correct <tr> in the DOM
    oob_marker = f'hx-swap-oob="outerHTML:#row-{queue_id}"'
    html = html.replace(f'id="row-{queue_id}"', f'id="row-{queue_id}" {oob_marker}', 1)
    return html


@router.delete("/queue/{queue_id}", response_class=HTMLResponse)
async def queue_remove(request: Request, queue_id: int) -> HTMLResponse:
    """Remove an entry from the download queue.

    Returns 200 with an empty OOB fragment that removes the row from the DOM.
    """
    try:
        with get_session() as session:
            remove_from_queue(session, queue_id)
    except ValueError:
        return HTMLResponse(
            content=make_toast("Queue entry not found.", "error"),
            status_code=404,
        )

    # Return an OOB swap that removes the row
    oob_html = f'<tr id="row-{queue_id}" hx-swap-oob="delete"></tr>'
    return HTMLResponse(content=oob_html + make_toast("Removed from queue.", "info"))


@router.post("/queue/{queue_id}/retry", response_class=HTMLResponse)
async def queue_retry(request: Request, queue_id: int) -> HTMLResponse:
    """Reset a failed queue entry back to pending.

    Returns an updated row partial via OOB swap.
    """
    try:
        with get_session() as session:
            retry_entry(session, queue_id)
    except ValueError:
        return HTMLResponse(
            content=make_toast("Queue entry not found.", "error"),
            status_code=404,
        )

    row_html = _render_queue_row_partial(request, queue_id)
    return HTMLResponse(content=row_html + make_toast("Retrying download…", "info"))


@router.patch("/queue/{queue_id}/priority", response_class=HTMLResponse)
async def queue_adjust_priority(
    request: Request,
    queue_id: int,
    delta: int = Form(...),
) -> HTMLResponse:
    """Adjust the priority of a queue entry by +1 or -1 (clamped to >= 0).

    Returns an updated row partial via OOB swap.
    """
    with get_session() as session:
        entry = session.get(DownloadQueue, queue_id)
        if entry is None:
            return HTMLResponse(
                content=make_toast("Queue entry not found.", "error"),
                status_code=404,
            )
        new_priority = max(0, entry.priority + delta)
        entry.priority = new_priority
        session.commit()

    row_html = _render_queue_row_partial(request, queue_id)
    return HTMLResponse(content=row_html)


# ── Story 9.2 — HTMX polling fragments ────────────────────────────────────────


@router.get("/queue/rows", response_class=HTMLResponse)
async def queue_rows_fragment(request: Request) -> HTMLResponse:
    """Return the queue table body inner HTML for HTMX polling.

    Renders ``partials/queue_rows_fragment.html`` — no base layout.
    """
    from file_fetcher.web.routes.queue import _fetch_queue_rows

    templates = request.app.state.templates
    entries = _fetch_queue_rows()
    return templates.TemplateResponse(
        request,
        "partials/queue_rows_fragment.html",
        {"entries": entries},
    )


@router.get("/queue/badge")
async def queue_badge() -> Response:
    """Return the count of active (pending + downloading) queue items.

    Returns plain text count, or empty string when count is 0 so the
    ``empty:hidden`` CSS class can hide the badge element.
    """
    with get_session() as session:
        count = (
            session.query(DownloadQueue)
            .filter(
                DownloadQueue.status.in_(
                    [DownloadStatus.PENDING, DownloadStatus.DOWNLOADING]
                )
            )
            .count()
        )
    content = str(count) if count > 0 else ""
    return Response(content=content, media_type="text/plain")


# ── Story 10.1 — settings toggle ─────────────────────────────────────────────


@router.patch("/settings/sftp_scan_enabled", response_class=HTMLResponse)
async def toggle_sftp_scan(value: str = Form(...)) -> HTMLResponse:
    """Immediately save the ``sftp_scan_enabled`` setting.

    Accepts ``value`` as a form field (``"true"`` / ``"false"`` or
    the string representation of a checkbox, e.g. ``"on"``).
    Returns a toast OOB fragment.
    """
    from file_fetcher.services import settings_service  # noqa: PLC0415

    enabled = value.lower() in ("true", "on", "1", "yes")
    with get_session() as session:
        settings_service.set(session, "sftp_scan_enabled", "true" if enabled else "false")

    label = "Scan enabled" if enabled else "Scan disabled"
    return HTMLResponse(content=make_toast(label, "success"))


# ── Story 10.2 — delete entry & full reset ────────────────────────────────────


@router.delete("/catalog/{catalog_id}", response_class=HTMLResponse)
async def catalog_delete(catalog_id: int) -> HTMLResponse:
    """Delete a catalog entry (movie or show) and all its child rows.

    Returns an HTMX ``HX-Redirect`` header pointing to the catalog root.
    """
    with get_session() as session:
        found = delete_catalog_entry(session, catalog_id)

    if not found:
        return HTMLResponse(
            content=make_toast("Entry not found.", "error"),
            status_code=404,
        )

    return Response(  # type: ignore[return-value]
        status_code=200,
        headers={"HX-Redirect": "/?toast=Entry+deleted"},
    )


@router.post("/catalog/reset", response_class=HTMLResponse)
async def catalog_reset() -> HTMLResponse:
    """Truncate all catalog tables (full reset).

    Returns an HTMX ``HX-Redirect`` header pointing back to settings.
    """
    with get_session() as session:
        full_reset(session)

    return Response(  # type: ignore[return-value]
        status_code=200,
        headers={"HX-Redirect": "/settings?toast=Database+reset+complete"},
    )


# ── Story 10.3 — title override & re-enrichment ───────────────────────────────


@router.patch("/catalog/{catalog_id}/override", response_class=HTMLResponse)
async def catalog_set_override(
    request: Request,
    catalog_id: int,
    override_title: str = Form(""),
    omdb_id: str = Form(""),
) -> HTMLResponse:
    """Save title override and optional OMDB ID for a catalog entry.

    Returns the updated ``override_section.html`` partial + a toast OOB fragment.
    """
    templates = request.app.state.templates

    with get_session() as session:
        found = set_override(session, catalog_id, override_title, omdb_id or None)

    if not found:
        return HTMLResponse(
            content=make_toast("Entry not found.", "error"),
            status_code=404,
        )

    with get_session() as session:
        entry = get_by_id(session, catalog_id)

    partial_html = templates.get_template("partials/override_section.html").render(
        {"entry": entry, "request": request, "edit_mode": False}
    )
    return HTMLResponse(content=partial_html + make_toast("Override saved.", "success"))


@router.post("/catalog/{catalog_id}/enrich", response_class=HTMLResponse)
async def catalog_enrich(request: Request, catalog_id: int) -> HTMLResponse:
    """Trigger immediate OMDB re-enrichment for a single catalog entry.

    Returns the updated ``override_section.html`` partial + a toast OOB fragment.
    Respects ``title_override``, ``year_override``, and ``override_omdb_id``.
    """
    templates = request.app.state.templates

    with get_session() as session:
        success, message = enrich_one(session, catalog_id)

    toast_type = "success" if success else "error"
    toast_msg = f"Enriched: {message}" if success else f"Enrichment failed: {message}"

    with get_session() as session:
        entry = get_by_id(session, catalog_id)

    if entry is None:
        return HTMLResponse(
            content=make_toast("Entry not found.", "error"),
            status_code=404,
        )

    partial_html = templates.get_template("partials/override_section.html").render(
        {"entry": entry, "request": request, "edit_mode": False}
    )
    return HTMLResponse(content=partial_html + make_toast(toast_msg, toast_type))
