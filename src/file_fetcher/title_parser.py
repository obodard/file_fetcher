"""Parse movie and TV show titles from filenames or folder names."""

import re

def parse_title_and_year(filename: str) -> tuple[str, int | None]:
    """
    Extract a clean title and year from a file or folder name.
    
    Examples:
        - `Good Bye Lenin! (2003) (Good Bye, Lenin!) 1080p...` -> (`Good Bye Lenin!`, 2003)
        - `The.Secret.Agent.2025.SUBFRENCH...` -> (`The Secret Agent`, 2025)
    """
    # Remove file extension if present (e.g., .mkv, .mp4, .nfo)
    filename = re.sub(r'\.[a-zA-Z0-9]{2,4}$', '', filename)
    
    # Replace dots and underscores with spaces
    cleaned = filename.replace('.', ' ').replace('_', ' ')
    
    # Try to find a year (19xx or 20xx) with surrounding context
    # Usually year is in the format (YYYY) or [YYYY] or just YYYY
    year_match = re.search(r'[\(\[\s]?(19\d{2}|20\d{2})[\)\]\s]?', cleaned)
    year = None
    
    if year_match:
        year = int(year_match.group(1))
        # The title is usually everything before the year
        cutoff = year_match.start()
        title_part = cleaned[:cutoff].strip()
        if not title_part:
            # If the year is the first thing, maybe the title comes after
            title_part = cleaned
    else:
        title_part = cleaned

    # Strip resolution, codec, language tags from the end
    tags_re = re.compile(
        r'\b(1080p|720p|4k|2160p|x264|h264|h265|x265|hevc|ac3|dts|aac|multi|vostfr|subfrench|french|truefrench|webrip|hdrip|bluray|remux)\b', 
        flags=re.IGNORECASE
    )
    
    match = tags_re.search(title_part)
    if match:
        title_part = title_part[:match.start()]
        
    # Strip Season/Episode indicators like S01, S01E03, Season 1, etc.
    season_re = re.compile(r'\b(S\d{1,2}(E\d{1,2})?|Season\s*\d{1,2})\b', flags=re.IGNORECASE)
    match = season_re.search(title_part)
    if match:
        title_part = title_part[:match.start()]
    
    # Clean up trailing non-alphanumeric chars (braces, hyphens, extra spaces)
    title_part = re.sub(r'[\(\[\-\s]+$', '', title_part).strip()
    
    return title_part, year
