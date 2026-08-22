"""add protected document AI analysis jobs

Revision ID: 20260820_0010
Revises: 20260820_0009
Create Date: 2026-08-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260820_0010"
down_revision: Union[str, None] = "20260820_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "ai_analysis_jobs" in inspector.get_table_names():
        return

    op.create_table(
        "ai_analysis_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("artifact_id", sa.Integer(), nullable=False),
        sa.Column("task", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("stage", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("worker_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=30), nullable=False, server_default="protected-v1"),
        sa.Column("schema_version", sa.String(length=30), nullable=False, server_default="analysis-v1"),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
        sa.Column("retention", sa.String(length=30), nullable=False, server_default="delete_after_analysis"),
        sa.Column("consent_snapshot", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("usage", sa.JSON(), nullable=False),
        sa.Column("provider_file_name", sa.String(length=255), nullable=True),
        sa.Column("provider_file_uri", sa.Text(), nullable=True),
        sa.Column("provider_file_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_file_processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remote_cleanup_status", sa.String(length=30), nullable=False, server_default="not_applicable"),
        sa.Column("remote_cleanup_error", sa.Text(), nullable=True),
        sa.Column("provider_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("public_error", sa.Text(), nullable=True),
        sa.Column("private_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["artifact_id"], ["document_artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "user_id", "artifact_id", "task", "status", "provider_requested_at"):
        op.create_index(
            op.f(f"ix_ai_analysis_jobs_{column}"),
            "ai_analysis_jobs",
            [column],
            unique=False,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "ai_analysis_jobs" in inspector.get_table_names():
        op.drop_table("ai_analysis_jobs")
