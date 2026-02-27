"""Entry point for ``python -m file_fetcher``."""

from __future__ import annotations

import argparse
import os
import sys

from file_fetcher.config import load_config, load_search_config, setup_logging
from file_fetcher.scheduler import wait_until
from file_fetcher.sftp_client import SFTPDownloader
from file_fetcher.scanner import SFTPScanner
from file_fetcher.report import display_report_and_download
from file_fetcher.ratings import get_ratings


def handle_download() -> None:
    """Run the batch download flow."""
    # 1. Load configuration
    config = load_config()
    
    # Also attempt to load search config to mask those keys if they exist in env
    try:
        search_config = load_search_config()
    except Exception:
        search_config = None
        
    setup_logging(config, search_config)
    from file_fetcher import logger
    logger.info(f"Command executed: {' '.join(sys.argv)}")

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


def handle_search(query: str) -> None:
    """Run the intelligent media search flow via ADK agent."""
    config = load_config()
    search_config = load_search_config()
    setup_logging(config, search_config)
    from file_fetcher import logger
    logger.info(f"Command executed: {' '.join(sys.argv)}")

    # ADK reads GOOGLE_API_KEY from the environment automatically.
    # Ensure it is set (load_search_config already validated it).
    os.environ.setdefault("GOOGLE_API_KEY", search_config.google_api_key)

    try:
        with SFTPDownloader(config) as downloader:
            scanner = SFTPScanner(downloader)

            # Build the ADK agent with tools bound to this scanner/config
            from file_fetcher.agent import create_agent, run_agent

            print(f"\n🤖  Sending query to ADK agent (model: {search_config.gemini_model})…")
            agent = create_agent(
                scanner=scanner,
                omdb_api_key=search_config.omdb_api_key,
                model=search_config.gemini_model,
            )

            selected = run_agent(agent, query)

            if not selected:
                print("\n🔍  No media found matching your query.")
                return

            # The agent returns indices that reference the scanner's last result set.
            # Re-run a broad scan to get the full MediaEntry list, then pick the
            # entries/ratings the agent chose.
            #
            # Because the agent already called search_sftp_server (which ran
            # scanner.scan()), we re-scan with the same broad filters to rebuild
            # the list.  The agent's indices are relative to ITS search call, so
            # we need to replicate that.  For simplicity we do a fresh all-scan
            # and pair entries by title+year.
            all_entries = scanner.scan()
            entry_map = {
                (e.title, e.year): e for e in all_entries
            }

            matched_entries = []
            for item in selected:
                title = item.get("title", "")
                # Try exact match by title; fall back to index
                found = None
                for e in all_entries:
                    if e.title.lower() == title.lower():
                        found = e
                        break
                if found:
                    matched_entries.append(found)

            if not matched_entries:
                print("\n🔍  Agent selected items but they could not be mapped back to server entries.")
                return

            # Fetch ratings for the matched entries
            ratings_list = [
                get_ratings(e.title, e.year, search_config.omdb_api_key)
                for e in matched_entries
            ]

            display_report_and_download(matched_entries, ratings_list, config, downloader)
    except KeyboardInterrupt:
        print("\n\n⛔  Interrupted by user.")
        sys.exit(130)
    except Exception as exc:
        print(f"\n💥  Fatal error: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Run the File Fetcher CLI."""
    print()
    print("╔══════════════════════════════════════╗")
    print("║        📁  File Fetcher v0.2         ║")
    print("╚══════════════════════════════════════╝")
    print()

    parser = argparse.ArgumentParser(description="File Fetcher")
    subparsers = parser.add_subparsers(dest="command")
    
    # Download subcommand
    subparsers.add_parser("download", help="Batch download paths defined in files_to_download.txt")
    
    # Search subcommand
    search_parser = subparsers.add_parser("search", help="Intelligent media search")
    search_parser.add_argument("query", help="Natural language query (e.g. 'recent 2026 movies')")
    
    # If no arguments provided, default to download for backward compatibility
    if len(sys.argv) == 1:
        handle_download()
        return
        
    args = parser.parse_args()
    
    if args.command == "download":
        handle_download()
    elif args.command == "search":
        handle_search(args.query)


if __name__ == "__main__":
    main()
