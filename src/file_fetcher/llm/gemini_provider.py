"""Google Gemini LLM integration."""
import sys
from google import genai
from google.genai import types

from file_fetcher import logger
from file_fetcher.llm.base import LLMProvider, SearchFilters

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.client = genai.Client(api_key=api_key)
        
    def parse_query(self, user_query: str) -> SearchFilters:
        prompt = f"""
        Extract the following search parameters from the user's query about media:
        - media_type ('movies', 'tv', 'all'): defaults to 'all' if not specified.
        - year (integer): like 2026 if requested.
        - max_age_days (integer): numeric amount of days if they ask for 'recent', 'last X days', etc.
        - keywords: list of any other specific names or keywords.
        
        User query: "{user_query}"
        """
        try:
            logger.info("Sending query to Gemini API")
            logger.debug(f"Gemini prompt payload: {prompt}")
            
            response = self.client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SearchFilters,
                    temperature=0.0,
                ),
            )
            
            logger.debug(f"Gemini response payload: {response.text}")
            return SearchFilters.model_validate_json(response.text)
        except Exception as e:
            logger.error(f"Failed to parse query with Gemini: {e}")
            print(f"❌ Failed to parse query with Gemini: {e}", file=sys.stderr)
            sys.exit(1)
