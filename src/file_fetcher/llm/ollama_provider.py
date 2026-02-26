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
        - year (integer or null): MUST be null UNLESS the user explicitly types a precise 4-digit year (e.g., "1999" or "2025"). Phrases like "this year" or "recent" do NOT count as a year. If no explicit 4-digit year is found, return null.
        - max_age_days (integer): numeric amount of days if they ask for how recently it was uploaded/added. 
          If they say "recent" or "recently", use 30.
          If they say "uploaded this year", use 365.
        - keywords: list of EXACT strings that must appear in the filename (e.g. 1080p, x264). Do NOT put thematic or plot keywords here.
        - semantic_query (string): any descriptive, subjective, or thematic criteria that describes the content (e.g., "like Game of Thrones", "about knights", "sci-fi space movie"). Leave null if there is no semantic description.
        
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
                
            filters = SearchFilters.model_validate_json(content)
            
            # Programmatic safeguard: if the LLM hallucinated a year not in the query, strip it out.
            if filters.year is not None and str(filters.year) not in user_query:
                filters.year = None
                
            return filters
        except Exception as e:
            logger.error(f"Failed to parse query with Ollama: {e}")
            print(f"❌ Failed to parse query with Ollama: {e}", file=sys.stderr)
            sys.exit(1)

    def filter_candidates(self, semantic_query: str, candidates: list[dict]) -> list[int]:
        from pydantic import BaseModel
        class MatchResult(BaseModel):
            matching_indices: list[int]
            
        schema = MatchResult.model_json_schema()
        
        prompt = f"""
        You are an AI media assistant. The user is looking for media matching the following semantic query:
        "{semantic_query}"
        
        I have provided a JSON list of candidate media items below. Each candidate has an "index" and some metadata (title, plot, genre, actors, director, keywords).
        Evaluate each candidate against the semantic query.
        
        CRITICAL INSTRUCTIONS:
        - Be EXTREMELY strict. 
        - ONLY return the index of a candidate if its Plot, Genre, Title, or Actors strongly and definitively match the semantic query.
        - You MUST return NO MORE THAN 5 indices. If there are many matches, pick the absolute best 5.
        - Return ONLY valid JSON with a single list called "matching_indices" containing the integer indices of the matching candidates.
        - If none match, return an empty list: {{"matching_indices": []}}
        
        Candidates:
        {candidates}
        """
        try:
            logger.info("Sending candidate filter query to Ollama")
            logger.debug(f"Ollama filter payload: {prompt}")
            
            response = self.client.chat(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                format=schema,
                options={"temperature": 0.0}
            )
            
            content = response.message.content
            logger.debug(f"Ollama filter response: {content}")
            
            if not content:
                return [c["index"] for c in candidates]
                
            result = MatchResult.model_validate_json(content)
            
            # Safeguard: if LLM hallucinates and returns too many items, fall back to basic matching.
            if len(result.matching_indices) > 5:
                logger.warning(f"Ollama hallucinated {len(result.matching_indices)} matches. Falling back to simple text match.")
                query_lower = semantic_query.lower()
                fallback = []
                # strip out "like " or "about " from query for better fallback matching
                search_term = query_lower.replace("like ", "").replace("about ", "").strip()
                for c in candidates:
                    if search_term in str(c.get("title", "")).lower() or search_term in str(c.get("plot", "")).lower() or search_term in str(c.get("genre", "")).lower():
                        fallback.append(c["index"])
                return fallback

            return result.matching_indices
        except Exception as e:
            logger.error(f"Failed to filter candidates with Ollama: {e}")
            # Fallback to returning all if LLM fails
            return [c["index"] for c in candidates]
