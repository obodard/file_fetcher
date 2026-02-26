"""Base interfaces for LLM integration."""
import re
from typing import Literal
from pydantic import BaseModel, field_validator
from abc import ABC, abstractmethod

# Maximum allowed length for user queries sent to the LLM.
_MAX_QUERY_LENGTH = 500

# Maximum allowed value for max_age_days to prevent full-server enumeration.
_MAX_AGE_DAYS_CAP = 365


def sanitize_query(raw: str) -> str:
    """Sanitize a user query before interpolating it into an LLM prompt.

    - Strips ASCII/Unicode control characters (except normal whitespace).
    - Truncates to ``_MAX_QUERY_LENGTH`` characters.
    """
    # Remove control chars (C0, C1, DEL) but keep space/tab/newline
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', raw)
    return cleaned[:_MAX_QUERY_LENGTH]


class SearchFilters(BaseModel):
    media_type: Literal["movies", "tv", "all"] = "all"
    year: int | None = None
    max_age_days: int | None = None
    keywords: list[str] = []
    semantic_query: str | None = None

    @field_validator("max_age_days")
    @classmethod
    def cap_max_age_days(cls, v: int | None) -> int | None:
        if v is not None and v > _MAX_AGE_DAYS_CAP:
            return _MAX_AGE_DAYS_CAP
        return v


class LLMProvider(ABC):
    @abstractmethod
    def parse_query(self, user_query: str) -> SearchFilters:
        """Parse natural language query into structured SearchFilters."""
        pass
        
    @abstractmethod
    def filter_candidates(self, semantic_query: str, candidates: list[dict]) -> list[int]:
        """Filter a list of pre-fetched candidates based on OMDb metadata using semantic search."""
        pass
