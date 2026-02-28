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
    """Run the download queue flow (DB-backed)."""
    from dotenv import load_dotenv
    load_dotenv()

    config = load_config()
    try:
        search_config = load_search_config()
    except Exception:
        search_config = None
    setup_logging(config, search_config)
    from file_fetcher import logger
    logger.info(f"Command executed: {' '.join(sys.argv)}")

    print(f"📂  Download directory: {config.download_dir.resolve()}")
    print()

    from file_fetcher.db import get_session
    from file_fetcher.services import download_service

    try:
        with get_session() as session:
            with SFTPDownloader(config) as downloader:
                summary = download_service.process_queue(session, downloader, config.download_dir)
        print()
        print(
            f"📊  Summary: {summary['succeeded']} succeeded, "
            f"{summary['failed']} failed, "
            f"{summary['skipped']} skipped."
        )
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

    # Scan subcommand
    subparsers.add_parser("scan", help="Scan SFTP server and reconcile catalog")

    # Enrich subcommand
    enrich_parser = subparsers.add_parser("enrich", help="Enrich catalog entries with OMDB metadata")
    enrich_id_group = enrich_parser.add_mutually_exclusive_group()
    enrich_id_group.add_argument("--id", dest="movie_id", type=int, metavar="MOVIE_ID",
                                  help="Enrich a single movie (force re-fetch)")
    enrich_id_group.add_argument("--show", dest="show_id", type=int, metavar="SHOW_ID",
                                  help="Enrich a single show (force re-fetch)")

    # Override subcommand
    override_parser = subparsers.add_parser("override", help="Set title/year override for re-enrichment")
    override_id_group = override_parser.add_mutually_exclusive_group(required=True)
    override_id_group.add_argument("movie_id", nargs="?", type=int, metavar="MOVIE_ID",
                                    help="Movie PK to override")
    override_id_group.add_argument("--show", dest="show_id", type=int, metavar="SHOW_ID",
                                    help="Show PK to override")
    override_parser.add_argument("--title", type=str, help="New title override")
    override_parser.add_argument("--year", type=int, help="New year override")

    # Not-found subcommand
    subparsers.add_parser("not-found", help="Report all catalog entries OMDB could not match")

    # Delete subcommand
    delete_parser = subparsers.add_parser("delete", help="Delete a catalog entry and all its data")
    delete_id_group = delete_parser.add_mutually_exclusive_group(required=True)
    delete_id_group.add_argument("movie_id", nargs="?", type=int, metavar="MOVIE_ID",
                                  help="Movie PK to delete")
    delete_id_group.add_argument("--show", dest="show_id", type=int, metavar="SHOW_ID",
                                  help="Show PK to delete")

    # Reset subcommand
    subparsers.add_parser("reset", help="Reset the entire catalog database")

    # If no arguments provided, default to download for backward compatibility
    if len(sys.argv) == 1:
        handle_download()
        return

    # Delegate `queue` sub-command to the Click group before argparse parsing
    if len(sys.argv) >= 2 and sys.argv[1] == "queue":
        from file_fetcher.cli.queue_cmd import queue as queue_group
        # Pass remaining args (strip the program name)
        queue_group(sys.argv[2:], standalone_mode=True)
        return
        
    args = parser.parse_args()
    
    if args.command == "download":
        handle_download()
    elif args.command == "search":
        handle_search(args.query)
    elif args.command == "scan":
        from file_fetcher.cli.scan import run_scan
        run_scan()
    elif args.command == "enrich":
        from file_fetcher.cli.enrich import run_enrich
        run_enrich(movie_id=getattr(args, "movie_id", None), show_id=getattr(args, "show_id", None))
    elif args.command == "override":
        from file_fetcher.cli.override import run_override
        run_override(
            movie_id=getattr(args, "movie_id", None),
            show_id=getattr(args, "show_id", None),
            title=getattr(args, "title", None),
            year=getattr(args, "year", None),
        )
    elif args.command == "not-found":
        from file_fetcher.cli.enrich import run_not_found
        run_not_found()
    elif args.command == "delete":
        from file_fetcher.cli.delete import run_delete
        run_delete(
            movie_id=getattr(args, "movie_id", None),
            show_id=getattr(args, "show_id", None),
        )
    elif args.command == "reset":
        from file_fetcher.cli.delete import run_reset
        run_reset()


if __name__ == "__main__":
    main()
