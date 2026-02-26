"""Google Gemini LLM integration."""
import sys
from google import genai
from google.genai import types

from file_fetcher import logger
from file_fetcher.llm.base import LLMProvider, SearchFilters, sanitize_query

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model_name: str = 'gemini-2.5-flash'):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        
    def parse_query(self, user_query: str) -> SearchFilters:
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")
        safe_query = sanitize_query(user_query)
        prompt = f"""
        Extract the following search parameters from the user's query about media:
        - media_type ('movies', 'tv', 'all'): defaults to 'all' if not specified.
        - year (integer or null): MUST be null UNLESS the user explicitly types a precise 4-digit year (e.g., "1999" or "2025"). Phrases like "this year" or "recent" do NOT count as a year. If no explicit 4-digit year is found, return null.
        - max_age_days (integer): numeric amount of days if they ask for how recently it was uploaded/added. 
          CURRENT DATE: {current_date}. If they give a specific date (e.g. "since 2026-01-10"), calculate the number of days between that date and CURRENT DATE.
          If they use relative terms like "last week" (7 days), "last month" (30 days), "past 20 days" (20 days), calculate the appropriate number of days.
          If they say "recent" or "recently", use 30.
          If they say "uploaded this year", use 365.
        - keywords: list of EXACT strings that must appear in the filename (e.g. 1080p, x264). Do NOT put thematic or plot keywords here.
        - semantic_query (string): any descriptive, subjective, or thematic criteria that describes the content (e.g., "like Game of Thrones", "about knights", "sci-fi space movie"). Leave null if there is no semantic description.
        
        User query: "{safe_query}"
        """
        try:
            logger.info("Sending query to Gemini API")
            logger.debug(f"Gemini prompt payload: {prompt}")
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SearchFilters,
                    temperature=0.0,
                ),
            )
            
            logger.debug(f"Gemini response payload: {response.text}")
            filters = SearchFilters.model_validate_json(response.text)
            
            # Programmatic safeguard: if the LLM hallucinated a year not in the query, strip it out.
            if filters.year is not None and str(filters.year) not in user_query:
                filters.year = None
                
            return filters
        except Exception as e:
            logger.error(f"Failed to parse query with Gemini: {e}")
            print(f"❌ Failed to parse query with Gemini: {e}", file=sys.stderr)
            sys.exit(1)

    def filter_candidates(self, semantic_query: str, candidates: list[dict]) -> list[int]:
        from pydantic import BaseModel
        class MatchResult(BaseModel):
            matching_indices: list[int]
            
        prompt = f"""
        You are an AI media assistant. The user is looking for media matching the following semantic query:
        "{semantic_query}"
        
        I have provided a JSON list of candidate media items below. Each candidate has an "index" and some metadata (title, plot, genre, actors, director, keywords).
        Evaluate each candidate against the semantic query.
        
        CRITICAL INSTRUCTIONS:
        - Be EXTREMELY strict. 
        - ONLY return the index of a candidate if its Plot, Genre, Title, or Actors strongly and definitively match the semantic query.
        - Do NOT return all indices. It is very likely that only 1 or 2 items (or none) actually match.
        - Return ONLY valid JSON matching the schema, containing the integer indices of the candidates that are a good match for the query.
        - If none match, return an empty list.
        
        Candidates:
        {candidates}
        """
        try:
            logger.info("Sending candidate filter query to Gemini")
            logger.debug(f"Gemini filter payload: {prompt}")
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MatchResult,
                    temperature=0.0,
                ),
            )
            
            logger.debug(f"Gemini filter response: {response.text}")
            result = MatchResult.model_validate_json(response.text)
            
            # Safeguard: if LLM hallucinates and returns too many items, fall back to basic matching.
            if len(result.matching_indices) > 5:
                logger.warning(f"Gemini returned {len(result.matching_indices)} matches. Falling back to simple text match.")
                query_lower = semantic_query.lower()
                fallback = []
                search_term = query_lower.replace("like ", "").replace("about ", "").strip()
                for c in candidates:
                    if search_term in str(c.get("title", "")).lower() or search_term in str(c.get("plot", "")).lower() or search_term in str(c.get("genre", "")).lower():
                        fallback.append(c["index"])
                return fallback
                
            return result.matching_indices
        except Exception as e:
            logger.error(f"Failed to filter candidates with Gemini: {e}")
            # Fallback to returning all if LLM fails
            return [c["index"] for c in candidates]
