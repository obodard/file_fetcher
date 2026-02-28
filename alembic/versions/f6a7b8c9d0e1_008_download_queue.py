"""008_download_queue

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-02-28 12:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "download_queue",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("remote_file_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(length=2048), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(
            ["remote_file_id"],
            ["remote_files.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("remote_file_id", name="uq_dq_remote_file_id"),
    )
    op.create_index("ix_dq_status_priority", "download_queue", ["status", "priority"])


def downgrade() -> None:
    op.drop_index("ix_dq_status_priority", table_name="download_queue")
    op.drop_table("download_queue")
