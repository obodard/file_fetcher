"""Movie ORM model."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from file_fetcher.models.base import Base
from file_fetcher.models.enums import MediaType, OmdbStatus

log = logging.getLogger(__name__)


class Movie(Base):
    """Represents a catalogued film."""

    __tablename__ = "movies"
    __table_args__ = (
        UniqueConstraint("title", "year", name="uq_movies_title_year"),
        Index("ix_movies_title", "title"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    year: Mapped[Optional[int]] = mapped_column(nullable=True)
    media_type: Mapped[MediaType] = mapped_column(
        default=MediaType.film,
        server_default=MediaType.film.value,
    )
    title_override: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    year_override: Mapped[Optional[int]] = mapped_column(nullable=True)
    omdb_status: Mapped[OmdbStatus] = mapped_column(
        default=OmdbStatus.PENDING,
        server_default=OmdbStatus.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    omdb_data: Mapped[Optional["OmdbData"]] = relationship(  # noqa: F821
        "OmdbData", foreign_keys="OmdbData.movie_id", back_populates="movie", uselist=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Movie id={self.id} title={self.title!r} year={self.year}>"
