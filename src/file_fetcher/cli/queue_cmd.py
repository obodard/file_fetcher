"""CLI commands for managing the download queue.

Provides:
  file-fetcher queue add <identifier> [--priority N]
  file-fetcher queue list [--status STATUS]
  file-fetcher queue remove <queue_id>
  file-fetcher queue retry <queue_id> | --all-failed
  file-fetcher queue status
"""

from __future__ import annotations

import sys
from typing import Optional

import click

from file_fetcher.db import get_session
from file_fetcher.models.enums import DownloadStatus
from file_fetcher.models.remote_file import RemoteFile
from file_fetcher.services import queue_service


@click.group()
def queue() -> None:
    """Manage the download queue."""


# ── add ───────────────────────────────────────────────────────────────────────


@queue.command()
@click.argument("identifier")
@click.option("--priority", default=0, show_default=True, help="Queue priority (higher = sooner).")
def add(identifier: str, priority: int) -> None:
    """Add a remote file to the queue by path substring or numeric ID."""
    with get_session() as session:
        # Try numeric ID first
        remote_file: Optional[RemoteFile] = None
        try:
            rf_id = int(identifier)
            remote_file = session.get(RemoteFile, rf_id)
        except ValueError:
            pass

        if remote_file is None:
            # Path substring match
            matches = (
                session.query(RemoteFile)
                .filter(RemoteFile.remote_path.contains(identifier))
                .all()
            )
            if not matches:
                click.echo(f"No remote file found matching: {identifier!r}")
                sys.exit(1)
            if len(matches) > 1:
                click.echo(f"Multiple matches for {identifier!r}. Please be more specific:")
                for rf in matches:
                    click.echo(f"  [{rf.id}] {rf.remote_path}")
                sys.exit(1)
            remote_file = matches[0]

        # Determine the display title
        title = _title(remote_file)

        try:
            entry = queue_service.add_to_queue(session, remote_file.id, priority=priority)
        except ValueError as exc:
            click.echo(str(exc))
            sys.exit(1)

        # Check whether it was already in the queue (status already set means pre-existing)
        # We compare created_at == updated_at heuristic; simpler: check if it was just added
        # Actually add_to_queue returns existing without modifying it, and a brand-new entry
        # will have a very recent created_at. Instead, track whether we created it by checking
        # if the entry existed before the call: since we flushed on create, if the entry priority
        # matches and was not new we can't easily tell. Use a flag approach via the service.
        # Simple approach: check if entry priority matches and status is PENDING.
        # We'll detect "already queued" by seeing if the entry.id existed before creation
        # -- the cleanest signal is that add_to_queue returns an entry whose status is NOT pending
        # for pre-existing, but it could be pending too.
        # Best approach: re-query to see if created ~now. Alternative: expose a flag. For now
        # we check pending vs non-pending for the "already queued" message.
        if entry.status != DownloadStatus.PENDING:
            click.echo(f"Already in queue: {title!r} (status: {entry.status.value})")
        else:
            # Count position
            pending = queue_service.get_pending(session)
            position = next(
                (i + 1 for i, e in enumerate(pending) if e.id == entry.id),
                len(pending),
            )
            click.echo(f"Added to queue: {title!r} — position #{position}")


# ── list ──────────────────────────────────────────────────────────────────────


@queue.command("list")
@click.option(
    "--status",
    "status_filter",
    default=None,
    type=click.Choice([s.value for s in DownloadStatus], case_sensitive=False),
    help="Filter by status.",
)
def list_cmd(status_filter: Optional[str]) -> None:
    """List download queue entries."""
    with get_session() as session:
        status_enum = DownloadStatus(status_filter) if status_filter else None
        entries = queue_service.list_queue(session, status=status_enum)

        if not entries:
            click.echo("Download queue is empty.")
            return

        # Format table
        rows = []
        for i, entry in enumerate(entries, 1):
            rf = entry.remote_file
            title = _title(rf)
            remote_path = rf.remote_path
            if len(remote_path) > 45:
                remote_path = "…" + remote_path[-44:]
            created = entry.created_at.strftime("%Y-%m-%d %H:%M") if entry.created_at else ""
            rows.append([i, title[:30], remote_path, entry.status.value, entry.priority, created])

        headers = ["#", "Title", "Remote Path", "Status", "Priority", "Queued At"]

        try:
            from tabulate import tabulate
            click.echo(tabulate(rows, headers=headers, tablefmt="simple"))
        except ImportError:
            # Fallback: simple manual formatting
            widths = [max(len(str(r[i])) for r in ([headers] + rows)) for i in range(len(headers))]
            fmt = "  ".join(f"{{:<{w}}}" for w in widths)
            click.echo(fmt.format(*headers))
            click.echo("  ".join("-" * w for w in widths))
            for row in rows:
                click.echo(fmt.format(*[str(c) for c in row]))


# ── remove ────────────────────────────────────────────────────────────────────


@queue.command()
@click.argument("queue_id", type=int)
def remove(queue_id: int) -> None:
    """Remove a queue entry by its ID."""
    with get_session() as session:
        # Grab title before deleting
        from file_fetcher.models.download_queue import DownloadQueue
        entry = session.get(DownloadQueue, queue_id)
        if entry is None:
            click.echo(f"Queue entry #{queue_id} not found.")
            sys.exit(1)
        title = _title(entry.remote_file)
        try:
            queue_service.remove_from_queue(session, queue_id)
        except ValueError:
            click.echo(f"Queue entry #{queue_id} not found.")
            sys.exit(1)
        click.echo(f"Removed from queue: {title!r}")


# ── retry ─────────────────────────────────────────────────────────────────────


@queue.command()
@click.argument("queue_id", required=False, type=int, default=None)
@click.option("--all-failed", is_flag=True, default=False, help="Retry all failed entries.")
def retry(queue_id: Optional[int], all_failed: bool) -> None:
    """Retry a failed (or stuck) queue entry, or all failed entries."""
    if not queue_id and not all_failed:
        click.echo("Provide a queue_id or --all-failed.")
        sys.exit(1)

    with get_session() as session:
        if all_failed:
            count = queue_service.retry_all_failed(session)
            click.echo(f"Retried {count} failed entr{'ies' if count != 1 else 'y'}.")
        else:
            try:
                entry = queue_service.retry_entry(session, queue_id)  # type: ignore[arg-type]
            except ValueError as exc:
                click.echo(str(exc))
                sys.exit(1)
            title = _title(entry.remote_file)
            click.echo(f"Retried: {title!r} — moved back to pending.")


# ── status ────────────────────────────────────────────────────────────────────


@queue.command("status")
def status_cmd() -> None:
    """Show queue status counts."""
    with get_session() as session:
        summary = queue_service.get_queue_summary(session)
        click.echo(
            f"Queue: {summary['pending']} pending, "
            f"{summary['downloading']} downloading, "
            f"{summary['completed']} completed, "
            f"{summary['failed']} failed "
            f"({summary['total']} total)"
        )


# ── helpers ───────────────────────────────────────────────────────────────────


def _title(remote_file: RemoteFile) -> str:
    """Return the best available display title for a RemoteFile."""
    if remote_file.movie:
        m = remote_file.movie
        return f"{m.title} ({m.year})" if m.year else m.title
    if remote_file.show:
        s = remote_file.show
        return f"{s.title} ({s.year})" if s.year else s.title
    return remote_file.filename
