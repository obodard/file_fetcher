"""Catalog web routes — home page and grid rendering."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from file_fetcher.db import get_session
from file_fetcher.services.catalog import search_catalog

router = APIRouter()

_MEDIA_TYPE_MAP = {
    "movie": "film",
    "series": "series",
}


@router.get("/", response_class=HTMLResponse)
async def catalog_grid(
    request: Request,
    type: Optional[str] = Query(default=None, description="Filter: movie | series"),
    q: str = Query(default="", description="Search query"),
    genre: Optional[str] = Query(default=None),
    year_min: Optional[int] = Query(default=None),
    year_max: Optional[int] = Query(default=None),
    min_rating: Optional[float] = Query(default=None),
    availability: Optional[str] = Query(default=None),
    ai: int = Query(default=0),
) -> HTMLResponse:
    """Render the catalog poster grid page."""
    templates = request.app.state.templates

    # Map URL ?type= param to internal media_type values
    media_type = _MEDIA_TYPE_MAP.get(type or "", None)

    with get_session() as session:
        entries = search_catalog(session, query=q, media_type=media_type, limit=40)

    return templates.TemplateResponse(
        request,
        "catalog/grid.html",
        {
            "entries": entries,
            "current_type": type or "",
            "current_q": q,
            "current_genre": genre or "",
            "current_year_min": year_min or "",
            "current_year_max": year_max or "",
            "current_min_rating": min_rating or "",
            "current_availability": availability or "",
            "current_ai": ai,
            "title": "file_fetcher — Catalog",
        },
    )
