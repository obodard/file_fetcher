"""Progress display — tqdm wrapper for SFTP transfers."""

from __future__ import annotations

from tqdm import tqdm


class TransferProgress:
    """Wraps a ``tqdm`` bar and exposes a Paramiko-compatible callback."""

    def __init__(self, filename: str, total: int, initial: int = 0) -> None:
        self._bar = tqdm(
            total=total,
            initial=initial,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=filename,
            ncols=100,
            miniters=1,
        )

    def callback(self, bytes_transferred: int, total_bytes: int) -> None:
        """Paramiko transfer callback — called periodically during get/put."""
        self._bar.n = bytes_transferred
        self._bar.refresh()

    def update(self, chunk_size: int) -> None:
        """Manual update for chunked (resume) transfers."""
        self._bar.update(chunk_size)

    def close(self) -> None:
        self._bar.close()

    # Context-manager support
    def __enter__(self) -> "TransferProgress":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
