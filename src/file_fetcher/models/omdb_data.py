"""OmdbData ORM model — stores enrichment metadata from the OMDB API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from file_fetcher.models.base import Base

log = logging.getLogger(__name__)


class OmdbData(Base):
    """Cached OMDB enrichment data for a catalog entry (movie or show)."""

    __tablename__ = "omdb_data"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign keys — one of these is set; the other is NULL
    movie_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    show_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("shows.id", ondelete="CASCADE"), nullable=True, index=True
    )

    # Core OMDB fields (25 total)
    imdb_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    year: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    rated: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    released: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    runtime: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    genre: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    director: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    writer: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    actors: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    plot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    awards: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    imdb_rating: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    rotten_tomatoes_rating: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    metacritic_rating: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    imdb_votes: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    box_office: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    poster_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    dvd: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    production: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    total_seasons: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Poster/thumbnail image blobs (Story 2.3)
    poster_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    thumbnail_blob: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    poster_content_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    movie: Mapped[Optional["Movie"]] = relationship(  # noqa: F821
        "Movie", foreign_keys=[movie_id], back_populates="omdb_data"
    )
    show: Mapped[Optional["Show"]] = relationship(  # noqa: F821
        "Show", foreign_keys=[show_id], back_populates="omdb_data"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OmdbData id={self.id} movie_id={self.movie_id} show_id={self.show_id} title={self.title!r}>"
