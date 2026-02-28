"""007_local_files

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-28 12:04:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create local_files table."""
    op.create_table(
        "local_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=True),
        sa.Column("show_id", sa.Integer(), nullable=True),
        sa.Column("local_path", sa.String(1024), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("media_type", sa.String(50), nullable=False),
        sa.Column("source_directory", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("local_path"),
    )
    op.create_index("ix_local_files_movie_id", "local_files", ["movie_id"])
    op.create_index("ix_local_files_show_id", "local_files", ["show_id"])


def downgrade() -> None:
    """Drop local_files table."""
    op.drop_index("ix_local_files_show_id", table_name="local_files")
    op.drop_index("ix_local_files_movie_id", table_name="local_files")
    op.drop_table("local_files")
