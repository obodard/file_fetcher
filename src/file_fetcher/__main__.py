"""Entry point for ``python -m file_fetcher``."""

from __future__ import annotations

import sys

from file_fetcher.config import load_config
from file_fetcher.scheduler import wait_until
from file_fetcher.sftp_client import SFTPDownloader


def main() -> None:
    """Run the File Fetcher CLI."""

    print()
    print("╔══════════════════════════════════════╗")
    print("║        📁  File Fetcher v0.1         ║")
    print("╚══════════════════════════════════════╝")
    print()

    # 1. Load configuration
    config = load_config()

    if not config.remote_paths:
        print("Nothing to download — file list is empty.")
        sys.exit(0)

    print(f"📋  {len(config.remote_paths)} path(s) to download")
    print(f"📂  Destination: {config.download_dir.resolve()}")
    print()

    # 2. Wait if a schedule is set
    wait_until(config.scheduled_at)

    # 3. Connect and download
    try:
        with SFTPDownloader(config) as downloader:
            downloader.download_all()
            downloader.print_summary()
    except KeyboardInterrupt:
        print("\n\n⛔  Interrupted by user.")
        sys.exit(130)
    except Exception as exc:
        print(f"\n💥  Fatal error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
