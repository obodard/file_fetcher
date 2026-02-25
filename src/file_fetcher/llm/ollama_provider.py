"""Ollama local LLM integration."""
import sys
import ollama

from file_fetcher import logger
from file_fetcher.llm.base import LLMProvider, SearchFilters

class OllamaProvider(LLMProvider):
    def __init__(self, host: str, model_name: str):
        self.host = host
        self.model_name = model_name
        self.client = ollama.Client(host=host)
        
    def parse_query(self, user_query: str) -> SearchFilters:
        schema = SearchFilters.model_json_schema()
        
        prompt = f"""
        Extract the following search parameters from the user's query about media:
        - media_type ('movies', 'tv', 'all'): defaults to 'all' if not specified.
        - year (integer): like 2026 if requested.
        - max_age_days (integer): amount of days if they ask for 'last 30 days'. 
          If they say "recent", maybe 30 or 60 days.
        - keywords: list of any other specific names or keywords.
        
        Return ONLY valid JSON matching the schema. Do not include markdown formatting or commentary.
        
        User query: "{user_query}"
        """
        try:
            logger.info(f"Sending query to Ollama (model: {self.model_name})")
            logger.debug(f"Ollama prompt payload: {prompt}")
            
            response = self.client.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                format=schema,
                options={"temperature": 0.0}
            )
            
            content = response.message.content
            logger.debug(f"Ollama response payload: {content}")

            # ollama might return empty string if the model fails to adhere
            if not content:
                logger.warning("Empty response received from Ollama.")
                print("⚠️  Warning: empty response from Ollama. Using defaults.", file=sys.stderr)
                return SearchFilters()
                
            return SearchFilters.model_validate_json(content)
        except Exception as e:
            logger.error(f"Failed to parse query with Ollama: {e}")
            print(f"❌ Failed to parse query with Ollama: {e}", file=sys.stderr)
            sys.exit(1)
