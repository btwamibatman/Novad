"""add local document tool jobs

Revision ID: 20260804_0008
Revises: 20260724_0007
Create Date: 2026-08-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260804_0008"
down_revision: Union[str, None] = "20260724_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "tool_jobs" in inspector.get_table_names():
        return
    op.create_table(
        "tool_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("stage", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_content_type", sa.String(length=100), nullable=False),
        sa.Column("source_path", sa.String(length=500), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("findings", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("result_filename", sa.String(length=255), nullable=True),
        sa.Column("result_content_type", sa.String(length=100), nullable=True),
        sa.Column("result_path", sa.String(length=500), nullable=True),
        sa.Column("result_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("result_meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "user_id", "source_document_id", "kind", "status"):
        op.create_index(op.f(f"ix_tool_jobs_{column}"), "tool_jobs", [column], unique=False)


def downgrade() -> None:
    if "tool_jobs" in sa.inspect(op.get_bind()).get_table_names():
        op.drop_table("tool_jobs")
