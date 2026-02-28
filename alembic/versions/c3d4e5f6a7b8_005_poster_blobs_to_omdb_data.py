"""005_poster_blobs_to_omdb_data

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-28 12:02:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add poster and thumbnail blob columns to omdb_data table."""
    op.add_column("omdb_data", sa.Column("poster_blob", sa.LargeBinary(), nullable=True))
    op.add_column("omdb_data", sa.Column("thumbnail_blob", sa.LargeBinary(), nullable=True))
    op.add_column("omdb_data", sa.Column("poster_content_type", sa.String(50), nullable=True))


def downgrade() -> None:
    """Remove poster and thumbnail blob columns from omdb_data table."""
    op.drop_column("omdb_data", "poster_content_type")
    op.drop_column("omdb_data", "thumbnail_blob")
    op.drop_column("omdb_data", "poster_blob")
