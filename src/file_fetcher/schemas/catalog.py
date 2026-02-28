"""Pydantic schemas for catalog search and detail views.

Story 5.1: Catalog Service — Search & Availability Queries
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class CatalogResult(BaseModel):
    """Lightweight catalog entry returned by ``search_catalog``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    year: Optional[int] = None
    media_type: str
    omdb_status: str
    availability: str
    remote_paths: list[str]
    local_paths: list[str]

    # Optional enrichment display fields
    genre: Optional[str] = None
    director: Optional[str] = None
    actors: Optional[str] = None
    imdb_rating: Optional[str] = None
    poster_url: Optional[str] = None


class TitleDetail(BaseModel):
    """Full detail view for a single catalog entry including all OmdbData fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    year: Optional[int] = None
    media_type: str
    omdb_status: str
    availability: str
    remote_paths: list[str]
    local_paths: list[str]

    # OmdbData core fields
    imdb_id: Optional[str] = None
    imdb_rating: Optional[str] = None
    rotten_tomatoes_rating: Optional[str] = None
    metacritic_rating: Optional[str] = None
    genre: Optional[str] = None
    director: Optional[str] = None
    writer: Optional[str] = None
    actors: Optional[str] = None
    plot: Optional[str] = None
    language: Optional[str] = None
    country: Optional[str] = None
    awards: Optional[str] = None
    rated: Optional[str] = None
    released: Optional[str] = None
    runtime: Optional[str] = None
    poster_url: Optional[str] = None
    total_seasons: Optional[int] = None
    imdb_votes: Optional[str] = None
    box_office: Optional[str] = None

    # Override fields (Story 10.3)
    override_title: Optional[str] = None
    override_omdb_id: Optional[str] = None
