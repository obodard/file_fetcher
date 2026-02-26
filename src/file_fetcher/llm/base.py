"""Base interfaces for LLM integration."""
from typing import Literal
from pydantic import BaseModel
from abc import ABC, abstractmethod

class SearchFilters(BaseModel):
    media_type: Literal["movies", "tv", "all"] = "all"
    year: int | None = None
    max_age_days: int | None = None
    keywords: list[str] = []
    semantic_query: str | None = None

class LLMProvider(ABC):
    @abstractmethod
    def parse_query(self, user_query: str) -> SearchFilters:
        """Parse natural language query into structured SearchFilters."""
        pass
        
    @abstractmethod
    def filter_candidates(self, semantic_query: str, candidates: list[dict]) -> list[int]:
        """Filter a list of pre-fetched candidates based on OMDb metadata using semantic search."""
        pass
