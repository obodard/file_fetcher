"""006_omdb_status_to_shows

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-28 12:03:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add omdb_status column to shows table."""
    op.add_column(
        "shows",
        sa.Column(
            "omdb_status",
            sa.String(20),
            server_default="pending",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove omdb_status column from shows table."""
    op.drop_column("shows", "omdb_status")
