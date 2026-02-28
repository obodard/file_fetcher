"""Unit tests for MediaType enum (Story 1.2)."""

from file_fetcher.models.enums import MediaType


def test_media_type_film_value():
    """MediaType.film has string value 'film'."""
    assert MediaType.film.value == "film"
    assert MediaType.film == "film"


def test_media_type_series_value():
    """MediaType.series has string value 'series'."""
    assert MediaType.series.value == "series"
    assert MediaType.series == "series"


def test_media_type_is_str():
    """MediaType is a subclass of str."""
    assert isinstance(MediaType.film, str)
    assert isinstance(MediaType.series, str)


def test_media_type_members():
    """MediaType has exactly film and series members."""
    members = {m.value for m in MediaType}
    assert members == {"film", "series"}
