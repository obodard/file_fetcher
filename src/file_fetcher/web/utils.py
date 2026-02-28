"""Web layer utilities — shared helpers for API routes."""

from __future__ import annotations

from typing import Literal


def make_toast(
    message: str,
    type: Literal["success", "error", "info"] = "info",
) -> str:
    """Return an OOB HTML fragment that appends a DaisyUI toast alert.

    The fragment uses ``hx-swap-oob="beforeend:#toast-container"`` so HTMX
    inserts it at the end of ``#toast-container`` without any additional setup
    on the caller side.

    Args:
        message: Human-readable notification text.
        type:    ``"success"``, ``"error"``, or ``"info"``.  Maps to the
                 DaisyUI ``alert-{type}`` CSS modifier.

    Returns:
        HTML string fragment ready to append to an HTMX response body.
    """
    data_attr = ' data-toast-error="true"' if type == "error" else " data-toast"
    return (
        f'<div hx-swap-oob="beforeend:#toast-container">'
        f'<div role="alert" class="alert alert-{type} shadow-lg flex items-center gap-2 pr-2"'
        f'{data_attr}>'
        f'<span class="flex-1 text-sm">{message}</span>'
        f'<button aria-label="Dismiss" class="btn btn-ghost btn-xs" '
        f"onclick=\"this.closest('[role=alert]').remove()\">✕</button>"
        f"</div></div>"
    )
