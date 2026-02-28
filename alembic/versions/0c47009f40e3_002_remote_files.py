"""002_remote_files

Revision ID: 0c47009f40e3
Revises: 08cd8a0bf34f
Create Date: 2026-02-28 10:32:51.005457

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0c47009f40e3'
down_revision: Union[str, Sequence[str], None] = '08cd8a0bf34f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create remote_files table."""
    op.create_table(
        "remote_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=True),
        sa.Column("show_id", sa.Integer(), nullable=True),
        sa.Column("remote_path", sa.String(1024), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("media_type", sa.String(16), nullable=False),
        sa.Column("source_directory", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["show_id"], ["shows.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("remote_path", name="uq_remote_files_remote_path"),
    )


def downgrade() -> None:
    """Drop remote_files table."""
    op.drop_table("remote_files")

