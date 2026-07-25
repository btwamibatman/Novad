"""add adaptive OCR jobs and quality metadata

Revision ID: 20260724_0007
Revises: 20260718_0006
Create Date: 2026-07-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260724_0007"
down_revision: Union[str, None] = "20260718_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(
        column["name"] == column_name
        for column in inspector.get_columns(table_name)
    )


def upgrade() -> None:
    if not _column_exists("documents", "analysis_progress"):
        op.add_column(
            "documents",
            sa.Column(
                "analysis_progress",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )
    if not _column_exists("documents", "ai_summary_meta"):
        op.add_column(
            "documents",
            sa.Column(
                "ai_summary_meta",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )

    chunk_columns = (
        ("extraction_quality", sa.String(length=20), "'unknown'"),
        ("confidence", sa.Float(), None),
        ("table_count", sa.Integer(), "0"),
        ("uncertain_region_count", sa.Integer(), "0"),
    )
    for name, column_type, default in chunk_columns:
        if _column_exists("document_chunks", name):
            continue
        op.add_column(
            "document_chunks",
            sa.Column(
                name,
                column_type,
                nullable=name == "confidence",
                server_default=sa.text(default) if default is not None else None,
            ),
        )

    inspector = sa.inspect(op.get_bind())
    if "analysis_jobs" not in inspector.get_table_names():
        op.create_table(
            "analysis_jobs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("document_id", sa.Integer(), nullable=False),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="pending",
            ),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["document_id"], ["documents.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("document_id"),
        )
        op.create_index(
            op.f("ix_analysis_jobs_id"), "analysis_jobs", ["id"], unique=False
        )
        op.create_index(
            op.f("ix_analysis_jobs_document_id"),
            "analysis_jobs",
            ["document_id"],
            unique=True,
        )
        op.create_index(
            op.f("ix_analysis_jobs_status"),
            "analysis_jobs",
            ["status"],
            unique=False,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "analysis_jobs" in inspector.get_table_names():
        op.drop_index(op.f("ix_analysis_jobs_status"), table_name="analysis_jobs")
        op.drop_index(
            op.f("ix_analysis_jobs_document_id"), table_name="analysis_jobs"
        )
        op.drop_index(op.f("ix_analysis_jobs_id"), table_name="analysis_jobs")
        op.drop_table("analysis_jobs")

    for name in (
        "uncertain_region_count",
        "table_count",
        "confidence",
        "extraction_quality",
    ):
        if _column_exists("document_chunks", name):
            op.drop_column("document_chunks", name)
    if _column_exists("documents", "ai_summary_meta"):
        op.drop_column("documents", "ai_summary_meta")
    if _column_exists("documents", "analysis_progress"):
        op.drop_column("documents", "analysis_progress")
