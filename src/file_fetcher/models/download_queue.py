"""DownloadQueue ORM model — tracks files queued for download."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from file_fetcher.models.base import Base
from file_fetcher.models.enums import DownloadStatus

log = logging.getLogger(__name__)


class DownloadQueue(Base):
    """An entry in the download queue, referencing a RemoteFile."""

    __tablename__ = "download_queue"
    __table_args__ = (
        UniqueConstraint("remote_file_id", name="uq_dq_remote_file_id"),
        Index("ix_dq_status_priority", "status", "priority"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    remote_file_id: Mapped[int] = mapped_column(
        ForeignKey("remote_files.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[DownloadStatus] = mapped_column(
        default=DownloadStatus.PENDING,
        server_default=DownloadStatus.PENDING.value,
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    remote_file: Mapped["RemoteFile"] = relationship(  # noqa: F821
        "RemoteFile", lazy="select"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<DownloadQueue id={self.id} remote_file_id={self.remote_file_id}"
            f" status={self.status.value!r}>"
        )
