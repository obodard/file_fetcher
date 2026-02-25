"""OMDb API client for fetching IMDb and Rotten Tomatoes ratings."""

import requests
from dataclasses import dataclass

from file_fetcher import logger

@dataclass
class Ratings:
    imdb: str
    rotten_tomatoes: str
    genre: str = "N/A"
    rated: str = "N/A"
    runtime: str = "N/A"
    plot: str = "N/A"
    year: str = "N/A"
    director: str = "N/A"
    metacritic: str = "N/A"
    type: str = "N/A"
    language: str = "N/A"
    actors: str = "N/A"
    awards: str = "N/A"

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
        logger.info(f"Fetching OMDb ratings for title: '{title}', year: {year}")
        logger.debug(f"OMDb Request params: {params}")
        
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        
        logger.debug(f"OMDb Response: {data}")
        
        if data.get("Response") == "False":
            return Ratings("N/A", "N/A")
            
        imdb = data.get("imdbRating", "N/A")
        genre = data.get("Genre", "N/A")
        rated = data.get("Rated", "N/A")
        runtime = data.get("Runtime", "N/A")
        plot = data.get("Plot", "N/A")
        res_year = data.get("Year", "N/A")
        director = data.get("Director", "N/A")
        metacritic = data.get("Metascore", "N/A")
        type_str = data.get("Type", "N/A").capitalize()
        language = data.get("Language", "N/A")
        actors = data.get("Actors", "N/A")
        awards = data.get("Awards", "N/A")
        
        # truncate language if it's too long (e.g. "English, Spanish")
        if language != "N/A" and "," in language:
            language = language.split(",")[0]
        
        rt = "N/A"
        for rating in data.get("Ratings", []):
            if rating.get("Source") == "Rotten Tomatoes":
                rt = rating.get("Value", "N/A")
                break
                
        return Ratings(
            imdb=imdb, 
            rotten_tomatoes=rt,
            genre=genre,
            rated=rated,
            runtime=runtime,
            plot=plot,
            year=res_year,
            director=director,
            metacritic=metacritic,
            type=type_str,
            language=language,
            actors=actors,
            awards=awards
        )
    except Exception as exc:
        logger.error(f"Error fetching OMDb ratings for '{title}': {exc}")
        return Ratings("N/A", "N/A")
