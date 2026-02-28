"""Shared enumerations for ORM models."""

import enum


class MediaType(str, enum.Enum):
    """Distinguish between film and TV series catalog entries."""

    film = "film"
    series = "series"
