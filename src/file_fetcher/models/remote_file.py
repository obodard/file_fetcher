"""RemoteFile ORM model — tracks files discovered on the SFTP server."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from file_fetcher.models.base import Base
from file_fetcher.models.enums import MediaType

log = logging.getLogger(__name__)


class RemoteFile(Base):
    """A file path discovered on the SFTP server."""

    __tablename__ = "remote_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    movie_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("movies.id", ondelete="SET NULL"), nullable=True
    )
    show_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("shows.id", ondelete="SET NULL"), nullable=True
    )
    remote_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    media_type: Mapped[MediaType] = mapped_column(nullable=False)
    source_directory: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # back-references (lazy — no cascade needed here)
    movie: Mapped[Optional["Movie"]] = relationship("Movie", foreign_keys=[movie_id])  # noqa: F821
    show: Mapped[Optional["Show"]] = relationship("Show", foreign_keys=[show_id])  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RemoteFile id={self.id} path={self.remote_path!r}>"
