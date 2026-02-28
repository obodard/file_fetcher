"""003_omdb_data

Revision ID: a1b2c3d4e5f6
Revises: 0c47009f40e3
Create Date: 2026-02-28 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '0c47009f40e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create omdb_data table."""
    op.create_table(
        "omdb_data",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=True),
        sa.Column("show_id", sa.Integer(), nullable=True),
        sa.Column("imdb_id", sa.String(20), nullable=True),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("year", sa.String(20), nullable=True),
        sa.Column("rated", sa.String(20), nullable=True),
        sa.Column("released", sa.String(50), nullable=True),
        sa.Column("runtime", sa.String(30), nullable=True),
        sa.Column("genre", sa.String(255), nullable=True),
        sa.Column("director", sa.String(255), nullable=True),
        sa.Column("writer", sa.String(512), nullable=True),
        sa.Column("actors", sa.String(512), nullable=True),
        sa.Column("plot", sa.Text(), nullable=True),
        sa.Column("language", sa.String(255), nullable=True),
        sa.Column("country", sa.String(255), nullable=True),
        sa.Column("awards", sa.String(512), nullable=True),
        sa.Column("imdb_rating", sa.String(10), nullable=True),
        sa.Column("rotten_tomatoes_rating", sa.String(10), nullable=True),
        sa.Column("metacritic_rating", sa.String(10), nullable=True),
        sa.Column("imdb_votes", sa.String(30), nullable=True),
        sa.Column("box_office", sa.String(50), nullable=True),
        sa.Column("poster_url", sa.String(512), nullable=True),
        sa.Column("type", sa.String(30), nullable=True),
        sa.Column("dvd", sa.String(50), nullable=True),
        sa.Column("production", sa.String(255), nullable=True),
        sa.Column("website", sa.String(512), nullable=True),
        sa.Column("total_seasons", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_omdb_data_movie_id", "omdb_data", ["movie_id"])
    op.create_index("ix_omdb_data_show_id", "omdb_data", ["show_id"])


def downgrade() -> None:
    """Drop omdb_data table."""
    op.drop_index("ix_omdb_data_show_id", "omdb_data")
    op.drop_index("ix_omdb_data_movie_id", "omdb_data")
    op.drop_table("omdb_data")
