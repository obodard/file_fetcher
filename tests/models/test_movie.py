"""Unit tests for Movie model (Story 1.2)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from file_fetcher.models.enums import MediaType
from file_fetcher.models.movie import Movie


def test_movie_create_basic(db_session):
    """Movie can be created with minimum required fields."""
    movie = Movie(title="Inception", year=2010)
    db_session.add(movie)
    db_session.commit()
    assert movie.id is not None
    assert movie.title == "Inception"
    assert movie.year == 2010
    assert movie.media_type == MediaType.film


def test_movie_nullable_year(db_session):
    """Movie year is nullable."""
    movie = Movie(title="Unknown Year Film")
    db_session.add(movie)
    db_session.commit()
    assert movie.year is None


def test_movie_title_override(db_session):
    """Movie supports title and year overrides."""
    movie = Movie(title="Incepshun", year=2010, title_override="Inception", year_override=2010)
    db_session.add(movie)
    db_session.commit()
    assert movie.title_override == "Inception"
    assert movie.year_override == 2010


def test_movie_timestamps_set(db_session):
    """Movie created_at and updated_at are populated."""
    movie = Movie(title="Dune", year=2021)
    db_session.add(movie)
    db_session.commit()
    assert movie.created_at is not None
    assert movie.updated_at is not None


def test_movie_unique_constraint(db_session):
    """Cannot insert two movies with same title+year."""
    db_session.add(Movie(title="The Matrix", year=1999))
    db_session.commit()
    db_session.add(Movie(title="The Matrix", year=1999))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_movie_same_title_different_years(db_session):
    """Movies with same title but different years are allowed."""
    db_session.add(Movie(title="Star Wars", year=1977))
    db_session.add(Movie(title="Star Wars", year=2019))
    db_session.commit()
    count = db_session.query(Movie).filter_by(title="Star Wars").count()
    assert count == 2


def test_movie_default_media_type(db_session):
    """Default media_type is film."""
    movie = Movie(title="Parasite", year=2019)
    db_session.add(movie)
    db_session.commit()
    assert movie.media_type == MediaType.film
