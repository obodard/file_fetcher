"""Show, Season, and Episode ORM models."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from file_fetcher.models.base import Base
from file_fetcher.models.enums import MediaType, OmdbStatus

log = logging.getLogger(__name__)


class Show(Base):
    """Represents a catalogued TV series."""

    __tablename__ = "shows"
    __table_args__ = (
        UniqueConstraint("title", "year", name="uq_shows_title_year"),
        Index("ix_shows_title", "title"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    year: Mapped[Optional[int]] = mapped_column(nullable=True)
    media_type: Mapped[MediaType] = mapped_column(
        default=MediaType.series,
        server_default=MediaType.series.value,
    )
    title_override: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    year_override: Mapped[Optional[int]] = mapped_column(nullable=True)
    override_omdb_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
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
        "OmdbData", foreign_keys="OmdbData.show_id", back_populates="show", uselist=False
    )
    seasons: Mapped[list[Season]] = relationship(
        "Season", back_populates="show", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Show id={self.id} title={self.title!r} year={self.year}>"


class Season(Base):
    """A season belonging to a Show."""

    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    show_id: Mapped[int] = mapped_column(ForeignKey("shows.id", ondelete="CASCADE"), nullable=False)
    season_number: Mapped[int] = mapped_column(nullable=False)

    show: Mapped[Show] = relationship("Show", back_populates="seasons")
    episodes: Mapped[list[Episode]] = relationship(
        "Episode", back_populates="season", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Season id={self.id} show_id={self.show_id} season={self.season_number}>"


class Episode(Base):
    """An episode belonging to a Season."""

    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    episode_number: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    season: Mapped[Season] = relationship("Season", back_populates="episodes")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Episode id={self.id} season_id={self.season_id} ep={self.episode_number}>"
