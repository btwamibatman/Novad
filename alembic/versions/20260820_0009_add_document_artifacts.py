"""add verified document artifacts

Revision ID: 20260820_0009
Revises: 20260804_0008
Create Date: 2026-08-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260820_0009"
down_revision: Union[str, None] = "20260804_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "document_artifacts" not in inspector.get_table_names():
        op.create_table(
            "document_artifacts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("source_document_id", sa.Integer(), nullable=False),
            sa.Column(
                "kind",
                sa.String(length=30),
                nullable=False,
                server_default="protected_pdf",
            ),
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="verifying",
            ),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=100), nullable=False),
            sa.Column("stored_path", sa.String(length=500), nullable=False),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False),
            sa.Column("source_sha256", sa.String(length=64), nullable=False),
            sa.Column("artifact_sha256", sa.String(length=64), nullable=False),
            sa.Column("privacy_policy", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("policy_version", sa.String(length=30), nullable=False),
            sa.Column("detector_version", sa.String(length=60), nullable=False),
            sa.Column("coverage_report", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("verification_report", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("id", "user_id", "source_document_id", "kind", "status"):
            op.create_index(
                op.f(f"ix_document_artifacts_{column}"),
                "document_artifacts",
                [column],
                unique=False,
            )

    tool_columns = {column["name"] for column in inspector.get_columns("tool_jobs")}
    if "result_artifact_id" not in tool_columns:
        with op.batch_alter_table("tool_jobs") as batch_op:
            batch_op.add_column(sa.Column("result_artifact_id", sa.Integer(), nullable=True))
            batch_op.create_index(
                op.f("ix_tool_jobs_result_artifact_id"),
                ["result_artifact_id"],
                unique=False,
            )
            batch_op.create_foreign_key(
                "fk_tool_jobs_result_artifact_id_document_artifacts",
                "document_artifacts",
                ["result_artifact_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "tool_jobs" in inspector.get_table_names():
        tool_columns = {column["name"] for column in inspector.get_columns("tool_jobs")}
        if "result_artifact_id" in tool_columns:
            with op.batch_alter_table("tool_jobs") as batch_op:
                batch_op.drop_constraint(
                    "fk_tool_jobs_result_artifact_id_document_artifacts",
                    type_="foreignkey",
                )
                batch_op.drop_index(op.f("ix_tool_jobs_result_artifact_id"))
                batch_op.drop_column("result_artifact_id")
    if "document_artifacts" in inspector.get_table_names():
        op.drop_table("document_artifacts")
