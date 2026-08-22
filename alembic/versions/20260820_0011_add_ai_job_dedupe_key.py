"""add atomic AI analysis job dedupe key

Revision ID: 20260820_0011
Revises: 20260820_0010
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260820_0011"
down_revision: Union[str, None] = "20260820_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "ai_analysis_jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("ai_analysis_jobs")}
    if "dedupe_key" not in columns:
        op.add_column(
            "ai_analysis_jobs",
            sa.Column("dedupe_key", sa.String(length=64), nullable=True),
        )

    inspector = sa.inspect(op.get_bind())
    indexes = {
        index["name"] for index in inspector.get_indexes("ai_analysis_jobs")
    }
    if "ix_ai_analysis_jobs_dedupe_key" not in indexes:
        op.create_index(
            "ix_ai_analysis_jobs_dedupe_key",
            "ai_analysis_jobs",
            ["dedupe_key"],
            unique=True,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "ai_analysis_jobs" not in inspector.get_table_names():
        return
    indexes = {
        index["name"] for index in inspector.get_indexes("ai_analysis_jobs")
    }
    if "ix_ai_analysis_jobs_dedupe_key" in indexes:
        op.drop_index(
            "ix_ai_analysis_jobs_dedupe_key",
            table_name="ai_analysis_jobs",
        )
    columns = {column["name"] for column in inspector.get_columns("ai_analysis_jobs")}
    if "dedupe_key" in columns:
        op.drop_column("ai_analysis_jobs", "dedupe_key")
