"""OMDb API client for fetching IMDb and Rotten Tomatoes ratings."""

import requests
from dataclasses import dataclass

@dataclass
class Ratings:
    imdb: str
    rotten_tomatoes: str

def get_ratings(title: str, year: int | None, api_key: str) -> Ratings:
    """Fetch ratings from OMDb API."""
    if not api_key or api_key == "your_omdb_api_key":
        return Ratings("N/A", "N/A")
        
    url = "http://www.omdbapi.com/"
    params = {
        "t": title,
        "apikey": api_key
    }
    if year:
        params["y"] = str(year)
        
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("Response") == "False":
            return Ratings("N/A", "N/A")
            
        imdb = data.get("imdbRating", "N/A")
        rt = "N/A"
        for rating in data.get("Ratings", []):
            if rating.get("Source") == "Rotten Tomatoes":
                rt = rating.get("Value", "N/A")
                break
                
        return Ratings(imdb=imdb, rotten_tomatoes=rt)
    except Exception:
        return Ratings("N/A", "N/A")
