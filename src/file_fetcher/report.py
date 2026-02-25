"""CLI report generation and interactive download prompt."""
import sys
from typing import TYPE_CHECKING
from file_fetcher.scanner import MediaEntry
from file_fetcher.ratings import get_ratings

if TYPE_CHECKING:
    from file_fetcher.config import SearchConfig
    from file_fetcher.sftp_client import SFTPDownloader

def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    size = float(size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

def display_report_and_download(
    entries: list[MediaEntry], 
    search_config: "SearchConfig", 
    downloader: "SFTPDownloader"
) -> None:
    if not entries:
        print("\n🔍  No media found matching the criteria.")
        return
        
    # Pre-fetch all ratings so we can use them in both the summary and detail views
    entry_ratings = []
    
    for idx, entry in enumerate(entries, 1):
        ratings = get_ratings(entry.title, entry.year, search_config.omdb_api_key)
        entry_ratings.append(ratings)

    # Detailed section (First pass)
    print("\n🎬  Details:")
    for idx, (entry, ratings) in enumerate(zip(entries, entry_ratings), 1):
        actual_year = ratings.year if ratings.year != "N/A" else (str(entry.year) if entry.year else "N/A")
        print(f" {idx}. {entry.title} ({actual_year}) • {ratings.rated} • {ratings.runtime}")
        print(f"    Genre:    {ratings.genre}")
        print(f"    Director: {ratings.director}")
        print(f"    Actors:   {ratings.actors}")
        print(f"    Awards:   {ratings.awards}")
        
        # Format plot to not be too long
        plot_disp = ratings.plot
        if len(plot_disp) > 100:
            plot_disp = plot_disp[:97] + "..."
        print(f"    Plot:     {plot_disp}")
        
        print(f"    Ratings:  IMDb ({ratings.imdb}) | RT ({ratings.rotten_tomatoes}) | Metacritic ({ratings.metacritic})")
        print()
        
    # Table section
    print(f"{'─' * 110}")
    print(f" {'#':<3} | {'Title':<33} | {'Year':<5} | {'Type':<7} | {'Language':<10} | {'RT':<4} | {'IMDb':<4} | {'MC':<3} | {'Uploaded':<10}")
    print(f"{'─' * 110}")
    
    for idx, (entry, ratings) in enumerate(zip(entries, entry_ratings), 1):
        year_str = str(entry.year) if entry.year else "N/A"
        date_str = entry.modified_date.strftime("%Y-%m-%d")
        
        title_disp = entry.title
        if len(title_disp) > 31:
            title_disp = title_disp[:28] + "..."
            
        rt_disp = ratings.rotten_tomatoes.replace("%", "") if ratings.rotten_tomatoes != "N/A" else "N/A"
        
        print(f" {idx:<3} | {title_disp:<33} | {year_str:<5} | {ratings.type:<7} | {ratings.language:<10} | {rt_disp:<4} | {ratings.imdb:<4} | {ratings.metacritic:<3} | {date_str:<10}")

    print(f"{'─' * 110}")
    print(f"{len(entries)} items found.\n")
    
    while True:
        try:
            choice = input("📥  Enter numbers to download (e.g. 1,3), 'all', or 'q' to quit: ").strip().lower()
            if choice in ('q', 'quit', 'exit', ''):
                print("👋  Exiting.")
                return
                
            selected_indices = []
            if choice == 'all':
                selected_indices = range(1, len(entries) + 1)
            else:
                parts = choice.split(',')
                for p in parts:
                    if p.strip().isdigit():
                        selected_indices.append(int(p.strip()))
            
            selected_entries = [entries[i - 1] for i in selected_indices if 1 <= i <= len(entries)]
            
            if not selected_entries:
                print("⚠️  Invalid selection. Try again.")
                continue
                
            break
        except KeyboardInterrupt:
            print("\n⛔  Interrupted by user.")
            sys.exit(130)
            
    paths_to_download = [entry.remote_path for entry in selected_entries]
    print(f"\n🚀  Downloading {len(paths_to_download)} item(s)...")
    downloader.download_paths(paths_to_download)
    downloader.print_summary()
