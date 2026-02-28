"""Shared enumerations for ORM models."""

import enum


class MediaType(str, enum.Enum):
    """Distinguish between film and TV series catalog entries."""

    film = "film"
    series = "series"


class OmdbStatus(str, enum.Enum):
    """Enrichment status for a catalog entry."""

    PENDING = "pending"
    ENRICHED = "enriched"
    FAILED = "failed"
    NOT_FOUND = "not_found"


class DownloadStatus(str, enum.Enum):
    """Download queue entry status."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
