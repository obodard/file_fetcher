"""SFTP client — connect, download files/dirs with resume, retry, and progress."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path
from typing import TYPE_CHECKING

import paramiko

from file_fetcher.progress import TransferProgress

if TYPE_CHECKING:
    from file_fetcher.config import AppConfig

# 64 KiB chunks for resume transfers
_CHUNK_SIZE = 65_536


class SFTPDownloader:
    """Manages an SFTP session and downloads files with resume/retry/progress."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._transport: paramiko.Transport | None = None
        self._sftp: paramiko.SFTPClient | None = None

        # Counters
        self.succeeded = 0
        self.failed = 0
        self.skipped = 0

    # ── connection ────────────────────────────────────────────────────

    def connect(self) -> None:
        """Open an SFTP connection using password authentication."""
        print(f"🔗  Connecting to {self.config.sftp_host}:{self.config.sftp_port} …")
        self._transport = paramiko.Transport(
            (self.config.sftp_host, self.config.sftp_port)
        )
        self._transport.connect(
            username=self.config.sftp_user,
            password=self.config.sftp_password,
        )
        self._sftp = paramiko.SFTPClient.from_transport(self._transport)
        print("✅  Connected.\n")

    def disconnect(self) -> None:
        """Close the SFTP session."""
        if self._sftp:
            self._sftp.close()
        if self._transport:
            self._transport.close()
        print("\n🔌  Disconnected.")

    @property
    def sftp(self) -> paramiko.SFTPClient:
        assert self._sftp is not None, "Not connected — call connect() first."
        return self._sftp

    # ── public API ────────────────────────────────────────────────────

    def download_all(self) -> None:
        """Download every path in the file list."""
        total = len(self.config.remote_paths)
        for idx, remote_path in enumerate(self.config.remote_paths, 1):
            print(f"── [{idx}/{total}] {remote_path}")
            try:
                if self._is_dir(remote_path):
                    self._download_dir(remote_path)
                else:
                    local_path = self._local_path_for(remote_path)
                    self._download_file_with_retry(remote_path, local_path)
            except Exception as exc:
                print(f"   ❌  Failed: {exc}")
                self.failed += 1

    def print_summary(self) -> None:
        total = self.succeeded + self.failed + self.skipped
        print(f"\n{'─' * 50}")
        print(f"📊  Summary: {total} items processed")
        print(f"    ✅  {self.succeeded} downloaded")
        print(f"    ⏭️   {self.skipped} skipped (already complete)")
        print(f"    ❌  {self.failed} failed")

    # ── directory handling ────────────────────────────────────────────

    def _is_dir(self, remote_path: str) -> bool:
        """Check if a remote path is a directory."""
        try:
            st = self.sftp.stat(remote_path)
            return stat.S_ISDIR(st.st_mode)  # type: ignore[arg-type]
        except FileNotFoundError:
            print(f"   ⚠️  Path not found on server: {remote_path}")
            raise

    def _download_dir(self, remote_dir: str) -> None:
        """Recursively download a remote directory."""
        entries = self.sftp.listdir_attr(remote_dir)
        for entry in entries:
            remote_child = f"{remote_dir.rstrip('/')}/{entry.filename}"
            if stat.S_ISDIR(entry.st_mode):  # type: ignore[arg-type]
                self._download_dir(remote_child)
            else:
                local_path = self._local_path_for(remote_child)
                self._download_file_with_retry(remote_child, local_path)

    # ── single-file download ──────────────────────────────────────────

    def _download_file_with_retry(
        self, remote_path: str, local_path: Path
    ) -> None:
        """Download a single file with retry logic."""
        last_exc: Exception | None = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                self._download_file(remote_path, local_path)
                return  # success
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < self.config.max_retries:
                    wait = self.config.retry_delay * attempt
                    print(
                        f"   ⚠️  Attempt {attempt}/{self.config.max_retries} "
                        f"failed: {exc} — retrying in {wait:.0f}s …"
                    )
                    time.sleep(wait)

        # All retries exhausted
        print(
            f"   ❌  Failed after {self.config.max_retries} attempts: "
            f"{last_exc}"
        )
        self.failed += 1

    def _download_file(self, remote_path: str, local_path: Path) -> None:
        """Download (or resume) a single file with a progress bar."""

        # Ensure local directory exists
        local_path.parent.mkdir(parents=True, exist_ok=True)

        remote_stat = self.sftp.stat(remote_path)
        remote_size: int = remote_stat.st_size  # type: ignore[assignment]

        local_size = local_path.stat().st_size if local_path.exists() else 0

        if local_size == remote_size:
            print(f"   ⏭️   Already complete: {local_path.name}")
            self.skipped += 1
            return

        if local_size > 0 and local_size < remote_size:
            # Resume
            self._resume_download(remote_path, local_path, local_size, remote_size)
        else:
            # Full download (also handles local_size > remote_size by overwriting)
            self._full_download(remote_path, local_path, remote_size)

        self.succeeded += 1

    def _full_download(
        self, remote_path: str, local_path: Path, remote_size: int
    ) -> None:
        """Standard full file download with progress."""
        display_name = _short_name(remote_path)
        with TransferProgress(display_name, remote_size) as prog:
            self.sftp.get(
                remote_path,
                str(local_path),
                callback=prog.callback,
            )

    def _resume_download(
        self,
        remote_path: str,
        local_path: Path,
        local_size: int,
        remote_size: int,
    ) -> None:
        """Resume a partially downloaded file."""
        display_name = _short_name(remote_path)
        print(f"   🔄  Resuming from {local_size / (1024**2):.1f} MiB …")

        with (
            self.sftp.open(remote_path, "rb") as remote_file,
            TransferProgress(display_name, remote_size, initial=local_size) as prog,
            open(local_path, "ab") as local_file,
        ):
            remote_file.seek(local_size)
            while True:
                chunk = remote_file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                local_file.write(chunk)
                prog.update(len(chunk))

    # ── path helpers ──────────────────────────────────────────────────

    def _local_path_for(self, remote_path: str) -> Path:
        """Map a remote absolute path to a local download path.

        Example: /media/Films/Movie.mkv → ./downloads/media/Films/Movie.mkv
        """
        # Strip leading slashes to make it relative
        relative = remote_path.lstrip("/")
        return self.config.download_dir / relative

    # ── context manager ───────────────────────────────────────────────

    def __enter__(self) -> "SFTPDownloader":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.disconnect()


def _short_name(remote_path: str, max_len: int = 45) -> str:
    """Return a short display name for progress bars."""
    name = os.path.basename(remote_path)
    if len(name) > max_len:
        return name[: max_len - 3] + "…"
    return name
