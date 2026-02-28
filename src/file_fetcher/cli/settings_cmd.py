"""CLI commands for managing application settings.

Provides:
  file-fetcher settings list
  file-fetcher settings set <key> <value>
"""

from __future__ import annotations

import click

from file_fetcher.db import get_session
from file_fetcher.services import settings_service


@click.group()
def settings() -> None:
    """View and update application settings."""


@settings.command(name="list")
def list_settings() -> None:
    """Display all application settings."""
    from tabulate import tabulate

    with get_session() as session:
        rows = settings_service.get_all(session)

    if not rows:
        click.echo("No settings found. Run the app once to seed defaults.")
        return

    table = [
        (row.key, row.value if row.value is not None else "", row.description or "")
        for row in rows
    ]
    click.echo(tabulate(table, headers=["Key", "Value", "Description"], tablefmt="simple"))


@settings.command(name="set")
@click.argument("key")
@click.argument("value")
def set_setting(key: str, value: str) -> None:
    """Update a setting value.

    \b
    KEY   The setting key (e.g. sftp_scan_enabled)
    VALUE The new value to store
    """
    with get_session() as session:
        updated = settings_service.set(session, key, value)

    click.echo(f"✅  Setting updated: {updated.key!r} = {updated.value!r}")
