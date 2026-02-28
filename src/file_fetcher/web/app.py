"""FastAPI application factory for the file_fetcher web layer."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"

_DEFAULT_POLL_INTERVAL = 5


def _load_poll_interval() -> int:
    """Return ``web_poll_interval_seconds`` from the settings table, defaulting to 5."""
    try:
        from file_fetcher.db import get_session
        from file_fetcher.models.setting import Setting

        with get_session() as session:
            row = session.query(Setting).filter_by(key="web_poll_interval_seconds").first()
            if row and row.value:
                return int(row.value)
    except Exception:  # noqa: BLE001
        pass
    return _DEFAULT_POLL_INTERVAL


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(title="file_fetcher web", version="0.1.0")

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Register Jinja2 templates
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    # Attach templates to app state so routes can access them
    app.state.templates = templates

    # Default poll interval (seconds) — can be overridden from DB settings at startup
    app.state.poll_interval = _load_poll_interval()

    # Register routers
    from file_fetcher.web.routes.catalog import router as catalog_router
    from file_fetcher.web.routes.api import router as api_router
    from file_fetcher.web.routes.queue import router as queue_router
    from file_fetcher.web.routes.settings import router as settings_router

    app.include_router(catalog_router)
    app.include_router(api_router)
    app.include_router(queue_router)
    app.include_router(settings_router)

    # Custom 404 handler — renders a template instead of a bare JSON response
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "catalog/title_detail_404.html",
            {"title": "Not Found — file_fetcher"},
            status_code=404,
        )

    return app


# Module-level app instance used by uvicorn
app = create_app()
