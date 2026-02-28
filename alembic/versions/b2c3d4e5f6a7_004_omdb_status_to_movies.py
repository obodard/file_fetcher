"""004_omdb_status_to_movies

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-28 12:01:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add omdb_status column to movies table."""
    op.add_column(
        "movies",
        sa.Column(
            "omdb_status",
            sa.String(20),
            server_default="pending",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove omdb_status column from movies table."""
    op.drop_column("movies", "omdb_status")
