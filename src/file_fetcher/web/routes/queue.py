"""Queue web routes — queue management page."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import joinedload

from file_fetcher.db import get_session
from file_fetcher.models.download_queue import DownloadQueue
from file_fetcher.models.remote_file import RemoteFile

router = APIRouter()


@dataclass
class QueueRow:
    """Display-ready snapshot of a DownloadQueue entry."""

    id: int
    title: str
    catalog_id: Optional[int]
    status: str
    priority: int
    progress: int
    error_message: Optional[str]


def _queue_row_from_orm(item: DownloadQueue) -> QueueRow:
    """Convert a DownloadQueue ORM object (with eager-loaded relations) to QueueRow."""
    rf = item.remote_file

    # Derive display title & catalog_id
    if rf is not None and rf.movie is not None:
        title = rf.movie.title_override or rf.movie.title
        catalog_id = rf.movie_id
    elif rf is not None and rf.show is not None:
        title = rf.show.title_override or rf.show.title
        catalog_id = rf.show_id
    elif rf is not None:
        title = rf.filename
        catalog_id = None
    else:
        title = f"Queue #{item.id}"
        catalog_id = None

    # progress is not a DB column yet — default to 0
    progress = getattr(item, "progress", 0) or 0

    return QueueRow(
        id=item.id,
        title=title,
        catalog_id=catalog_id,
        status=item.status.value if hasattr(item.status, "value") else str(item.status),
        priority=item.priority,
        progress=int(progress),
        error_message=item.error_message,
    )


def _fetch_queue_rows() -> list[QueueRow]:
    """Query all DownloadQueue entries and return display-ready RowsList."""
    with get_session() as session:
        orm_items = (
            session.query(DownloadQueue)
            .options(
                joinedload(DownloadQueue.remote_file)
                .joinedload(RemoteFile.movie),
                joinedload(DownloadQueue.remote_file)
                .joinedload(RemoteFile.show),
            )
            .order_by(
                DownloadQueue.priority.desc(),  # type: ignore[union-attr]
                DownloadQueue.created_at.asc(),  # type: ignore[union-attr]
            )
            .all()
        )
        return [_queue_row_from_orm(item) for item in orm_items]


@router.get("/queue", response_class=HTMLResponse)
async def queue_page(request: Request) -> HTMLResponse:
    """Render the download queue management page."""
    templates = request.app.state.templates
    entries = _fetch_queue_rows()
    poll_interval = getattr(request.app.state, "poll_interval", 5)

    return templates.TemplateResponse(
        request,
        "queue/queue.html",
        {
            "entries": entries,
            "poll_interval": poll_interval,
            "title": "Download Queue — file_fetcher",
        },
    )
