"""Unit tests for Show, Season, Episode models (Story 1.2)."""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from file_fetcher.models.enums import MediaType
from file_fetcher.models.show import Episode, Season, Show


def test_show_create_basic(db_session):
    """Show can be created with minimum required fields."""
    show = Show(title="Breaking Bad", year=2008)
    db_session.add(show)
    db_session.commit()
    assert show.id is not None
    assert show.media_type == MediaType.series


def test_show_with_seasons(db_session):
    """Show → Season relationship works."""
    show = Show(title="Chernobyl", year=2019)
    season = Season(season_number=1)
    show.seasons.append(season)
    db_session.add(show)
    db_session.commit()

    fetched = db_session.query(Show).filter_by(title="Chernobyl").one()
    assert len(fetched.seasons) == 1
    assert fetched.seasons[0].season_number == 1


def test_season_with_episodes(db_session):
    """Season → Episode relationship works."""
    show = Show(title="Dark", year=2017)
    season = Season(season_number=1)
    ep1 = Episode(episode_number=1, title="Secrets")
    ep2 = Episode(episode_number=2, title="Lies")
    season.episodes.extend([ep1, ep2])
    show.seasons.append(season)
    db_session.add(show)
    db_session.commit()

    fetched_season = db_session.query(Season).filter_by(season_number=1).one()
    assert len(fetched_season.episodes) == 2
    titles = {ep.title for ep in fetched_season.episodes}
    assert titles == {"Secrets", "Lies"}


def test_show_cascade_delete(db_session):
    """Deleting a Show cascades to Season and Episode."""
    show = Show(title="Fleabag", year=2016)
    season = Season(season_number=1)
    episode = Episode(episode_number=1, title="Pilot")
    season.episodes.append(episode)
    show.seasons.append(season)
    db_session.add(show)
    db_session.commit()

    db_session.delete(show)
    db_session.commit()

    assert db_session.query(Season).count() == 0
    assert db_session.query(Episode).count() == 0


def test_episode_nullable_title(db_session):
    """Episode title is nullable."""
    show = Show(title="Westworld", year=2016)
    season = Season(season_number=1)
    episode = Episode(episode_number=1)
    season.episodes.append(episode)
    show.seasons.append(season)
    db_session.add(show)
    db_session.commit()
    assert episode.title is None


def test_show_unique_constraint(db_session):
    """Cannot insert two shows with same title+year."""
    db_session.add(Show(title="Twin Peaks", year=1990))
    db_session.commit()
    db_session.add(Show(title="Twin Peaks", year=1990))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
