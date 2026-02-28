"""001_initial_schema

Revision ID: 08cd8a0bf34f
Revises: 
Create Date: 2026-02-28 10:29:39.522875

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '08cd8a0bf34f'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create movies, shows, seasons, episodes tables."""
    op.create_table(
        "movies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("media_type", sa.String(16), server_default="film", nullable=False),
        sa.Column("title_override", sa.String(512), nullable=True),
        sa.Column("year_override", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("title", "year", name="uq_movies_title_year"),
    )
    op.create_index("ix_movies_title", "movies", ["title"])

    op.create_table(
        "shows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("media_type", sa.String(16), server_default="series", nullable=False),
        sa.Column("title_override", sa.String(512), nullable=True),
        sa.Column("year_override", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("title", "year", name="uq_shows_title_year"),
    )
    op.create_index("ix_shows_title", "shows", ["title"])

    op.create_table(
        "seasons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("show_id", sa.Integer(), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "episodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("season_id", sa.Integer(), nullable=False),
        sa.Column("episode_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop movies, shows, seasons, episodes tables."""
    op.drop_table("episodes")
    op.drop_table("seasons")
    op.drop_index("ix_shows_title", "shows")
    op.drop_table("shows")
    op.drop_index("ix_movies_title", "movies")
    op.drop_table("movies")

