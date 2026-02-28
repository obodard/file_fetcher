"""Setting ORM model — key/value store for runtime configuration."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from file_fetcher.models.base import Base


class Setting(Base):
    """Represents a single application configuration setting."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Setting key={self.key!r} value={self.value!r}>"
