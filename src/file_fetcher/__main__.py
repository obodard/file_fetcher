"""Entry point for ``python -m file_fetcher``."""

from __future__ import annotations

import argparse
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
    """Run the intelligent media search flow."""
    config = load_config()
    search_config = load_search_config()
    setup_logging(config, search_config)
    
    print(f"\n🧠  Parsing query with {search_config.llm_provider}...")
    if search_config.llm_provider == "ollama":
        from file_fetcher.llm.ollama_provider import OllamaProvider
        provider = OllamaProvider(search_config.ollama_host, search_config.ollama_model)
    elif search_config.llm_provider == "gemini":
        from file_fetcher.llm.gemini_provider import GeminiProvider
        provider = GeminiProvider(search_config.gemini_api_key, search_config.gemini_model)
    else:
        print(f"❌  Unknown LLM provider: {search_config.llm_provider}")
        sys.exit(1)
        
    filters = provider.parse_query(query)
    
    try:
        with SFTPDownloader(config) as downloader:
            print("\n📡  Scanning server for matching media...")
            scanner = SFTPScanner(downloader)
            entries = scanner.scan(filters)
            
            # Pre-fetch OMDb metadata. We need it for both post-filtering (if applicable) and reporting.
            ratings_list = [
                get_ratings(e.title, e.year, search_config.omdb_api_key) for e in entries
            ]
            
            if filters.semantic_query and entries:
                print(f"🕵️  Post-filtering {len(entries)} items based on semantic query...")
                candidates = []
                for i, (entry, rating) in enumerate(zip(entries, ratings_list)):
                    candidates.append({
                        "index": i,
                        "title": entry.title,
                        "plot": rating.plot,
                        "genre": rating.genre,
                        "actors": rating.actors,
                        "director": rating.director
                    })
                    
                matched_indices = provider.filter_candidates(filters.semantic_query, candidates)
                
                # Keep only matched entries
                entries = [entries[i] for i in matched_indices if 0 <= i < len(entries)]
                ratings_list = [ratings_list[i] for i in matched_indices if 0 <= i < len(ratings_list)]
            
            display_report_and_download(entries, ratings_list, search_config, downloader)
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
