"""Scheduler — optionally wait until a target date/time before starting."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional


def wait_until(target: Optional[datetime]) -> None:
    """Block until *target*, or return immediately if ``None`` / in the past.

    Prints a human-readable countdown message while waiting.
    """
    if target is None:
        return

    now = datetime.now()
    delta = (target - now).total_seconds()

    if delta <= 0:
        print(f"⏰  Scheduled time ({target:%Y-%m-%d %H:%M}) already passed — starting now.")
        return

    _pretty_wait(target, delta)


def _pretty_wait(target: datetime, seconds: float) -> None:
    """Print the wait message and sleep."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")

    eta = " ".join(parts)
    print(f"⏳  Download scheduled for {target:%Y-%m-%d %H:%M}. Waiting {eta} …")

    try:
        time.sleep(seconds)
    except KeyboardInterrupt:
        print("\n⛔  Cancelled by user during wait.")
        raise SystemExit(0)

    print("🚀  Scheduled time reached — starting download.")
