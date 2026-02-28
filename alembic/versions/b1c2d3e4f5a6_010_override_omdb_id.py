"""010_override_omdb_id

Adds ``override_omdb_id`` column to ``movies`` and ``shows`` tables
so that users can specify a direct IMDB ID for re-enrichment via the web UI.

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f7
Create Date: 2026-02-28 19:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "movies",
        sa.Column("override_omdb_id", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "shows",
        sa.Column("override_omdb_id", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shows", "override_omdb_id")
    op.drop_column("movies", "override_omdb_id")
