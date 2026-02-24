from unittest.mock import patch, Mock
from file_fetcher.ratings import get_ratings, Ratings

@patch("file_fetcher.ratings.requests.get")
def test_get_ratings_success(mock_get):
    mock_resp = Mock()
    mock_resp.json.return_value = {
        "Response": "True",
        "imdbRating": "8.1",
        "Ratings": [{"Source": "Rotten Tomatoes", "Value": "92%"}]
    }
    mock_get.return_value = mock_resp
    
    ratings = get_ratings("Test Movie", 2026, "fake_key")
    assert ratings.imdb == "8.1"
    assert ratings.rotten_tomatoes == "92%"

@patch("file_fetcher.ratings.requests.get")
def test_get_ratings_not_found(mock_get):
    mock_resp = Mock()
    mock_resp.json.return_value = {"Response": "False", "Error": "Movie not found!"}
    mock_get.return_value = mock_resp
    
    ratings = get_ratings("Unknown", None, "fake_key")
    assert ratings.imdb == "N/A"
    assert ratings.rotten_tomatoes == "N/A"

def test_get_ratings_no_api_key():
    ratings = get_ratings("Test", 2026, "")
    assert ratings.imdb == "N/A"
    assert ratings.rotten_tomatoes == "N/A"

def test_get_ratings_default_api_key():
    ratings = get_ratings("Test", 2026, "your_omdb_api_key")
    assert ratings.imdb == "N/A"
    assert ratings.rotten_tomatoes == "N/A"
