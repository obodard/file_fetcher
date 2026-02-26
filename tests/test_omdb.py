import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("OMDB_API_KEY")

url = "http://www.omdbapi.com/"
params = {"t": "A Knight of the Seven Kingdoms", "apikey": api_key}
print(requests.get(url, params=params).json())
