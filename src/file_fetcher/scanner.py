"""Scan SFTP server for media files based on parsed LLM filters."""
from dataclasses import dataclass
from datetime import datetime
import stat
from typing import TYPE_CHECKING
import paramiko

from file_fetcher import logger
from file_fetcher.title_parser import parse_title_and_year

if TYPE_CHECKING:
    from file_fetcher.sftp_client import SFTPDownloader

@dataclass
class MediaEntry:
    title: str
    year: int | None
    remote_path: str
    modified_date: datetime
    size_bytes: int
    media_type: str


def scan_remote_path(
    sftp: paramiko.SFTPClient,
    base_dir: str,
) -> list[tuple[str, str, str]]:
    """Scan a single remote directory and return raw file tuples.

    Returns:
        List of ``(remote_path, filename, source_directory)`` tuples.
        No filtering or DB interaction — pure data retrieval.
    """
    results: list[tuple[str, str, str]] = []
    try:
        entries = sftp.listdir_attr(base_dir)
    except FileNotFoundError:
        logger.warning(f"Remote directory not found: {base_dir}")
        return results
    except Exception as exc:
        logger.warning(f"Failed to list remote directory {base_dir!r}: {exc}")
        return results

    for entry in entries:
        filename = entry.filename
        remote_path = f"{base_dir}/{filename}"
        results.append((remote_path, filename, base_dir))

    logger.debug(f"scan_remote_path({base_dir!r}): {len(results)} entries")
    return results


class SFTPScanner:
    """Scans the designated media folders over SFTP."""
    
    def __init__(self, downloader: "SFTPDownloader"):
        self.sftp = downloader.sftp
        
    def scan(self, media_type: str = "all", year: int | None = None, max_age_days: int | None = None, keywords: list[str] | None = None) -> list[MediaEntry]:
        """Find media matching the criteria."""
        # Define base dirs based on media type
        base_dirs = []
        if media_type in ("movies", "all"):
            base_dirs.extend(["Media1/Films", "Media2/Films", "Media1/4k", "Media2/4k"])
        if media_type in ("tv", "all"):
            base_dirs.extend(["Media1/Séries TV", "Media2/Séries TV"])
            
        results = []
        now = datetime.now()
        
        for base_dir in base_dirs:
            try:
                logger.debug(f"SFTP listdir_attr: {base_dir}")
                entries = self.sftp.listdir_attr(base_dir)
            except FileNotFoundError:
                continue
                
            for entry in entries:
                filename = entry.filename
                
                # Exclude .nfo files or tiny info files if needed (usually we care about the directory name)
                # But here we assume each entry at the root of a media folder is a movie/show.
                mtime = entry.st_mtime
                mod_date = datetime.fromtimestamp(mtime)
                
                # Filter by max age
                if max_age_days is not None:
                    age_days = (now - mod_date).days
                    if age_days > max_age_days:
                        continue
                        
                title, parsed_year = parse_title_and_year(filename)
                
                # Filter by year
                if year is not None and parsed_year != year:
                    continue
                    
                # Filter by keywords
                if keywords:
                    lower_filename = filename.lower()
                    if not all(kw.lower() in lower_filename for kw in keywords):
                        continue
                
                entry_media_type = "tv" if "Séries TV" in base_dir else "movie"
                
                results.append(MediaEntry(
                    title=title,
                    year=parsed_year,
                    remote_path=f"{base_dir}/{filename}",
                    modified_date=mod_date,
                    size_bytes=entry.st_size,
                    media_type=entry_media_type
                ))
                
        logger.info(f"Discovered {len(results)} raw media entries matching file-system filters: {[r.title for r in results]}")
        return results
