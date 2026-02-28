"""Settings web routes — view and edit application configuration."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from file_fetcher.db import get_session
from file_fetcher.services import settings_service
from file_fetcher.services.catalog import get_not_found
from file_fetcher.web.utils import validate_cron

log = logging.getLogger(__name__)

router = APIRouter()

# Settings that contain sensitive values — displayed as masked in the UI.
_SENSITIVE_KEYS = {"sftp_password", "omdb_api_key"}

# Cron-expression fields — validated when submitted.
_CRON_KEYS = {"sftp_scan_cron", "omdb_enrich_cron"}


@router.get("/settings", response_class=HTMLResponse)
async def settings_get(
    request: Request,
    toast: Optional[str] = Query(default=None),
) -> HTMLResponse:
    """Render the settings page.

    Loads all settings from the DB and passes them as a key→value dict.
    ``?toast=message`` query param (set on redirect-after-POST) shows a
    success notification via the Jinja2 template pre-render.
    """
    templates = request.app.state.templates

    with get_session() as session:
        all_settings = settings_service.get_all(session)
        not_found_entries = get_not_found(session)

    settings_dict = {s.key: (s.value or "") for s in all_settings}

    return templates.TemplateResponse(
        request,
        "settings/settings.html",
        {
            "settings": settings_dict,
            "sensitive_keys": _SENSITIVE_KEYS,
            "toast": toast,
            "not_found_entries": not_found_entries,
            "title": "Settings — file_fetcher",
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def settings_post(
    request: Request,
    sftp_host: str = Form(""),
    sftp_port: str = Form(""),
    sftp_user: str = Form(""),
    sftp_password: str = Form(""),
    sftp_remote_path: str = Form(""),
    sftp_scan_cron: str = Form(""),
    omdb_api_key: str = Form(""),
    omdb_batch_limit: str = Form(""),
    omdb_daily_quota: str = Form(""),
    omdb_enrich_cron: str = Form(""),
    download_dir: str = Form(""),
    scheduler_poll_interval: str = Form(""),
    web_poll_interval_seconds: str = Form(""),
) -> HTMLResponse:
    """Process settings form submission.

    Validates cron expressions; on error re-renders the form with 422 and
    inline field errors.  On success saves all fields and redirects to
    ``GET /settings`` with a success toast.
    """
    templates = request.app.state.templates

    # Collect all form data
    form_data = {
        "sftp_host": sftp_host,
        "sftp_port": sftp_port,
        "sftp_user": sftp_user,
        "sftp_password": sftp_password,
        "sftp_remote_path": sftp_remote_path,
        "sftp_scan_cron": sftp_scan_cron,
        "omdb_api_key": omdb_api_key,
        "omdb_batch_limit": omdb_batch_limit,
        "omdb_daily_quota": omdb_daily_quota,
        "omdb_enrich_cron": omdb_enrich_cron,
        "download_dir": download_dir,
        "scheduler_poll_interval": scheduler_poll_interval,
        "web_poll_interval_seconds": web_poll_interval_seconds,
    }

    # Validate cron expressions
    errors: dict[str, str] = {}
    for cron_key in _CRON_KEYS:
        val = form_data.get(cron_key, "")
        if val and not validate_cron(val):
            errors[cron_key] = (
                "Invalid cron expression. Use 5 space-separated fields "
                "(e.g. '0 3 * * *') or leave blank to disable."
            )

    if errors:
        # Re-render with validation errors
        with get_session() as session:
            not_found_entries = get_not_found(session)

        return templates.TemplateResponse(
            request,
            "settings/settings.html",
            {
                "settings": form_data,
                "sensitive_keys": _SENSITIVE_KEYS,
                "errors": errors,
                "toast": None,
                "not_found_entries": not_found_entries,
                "title": "Settings — file_fetcher",
            },
            status_code=422,
        )

    # Save all settings
    with get_session() as session:
        settings_service.update_batch(session, form_data)

    return RedirectResponse("/settings?toast=Settings+saved", status_code=303)
