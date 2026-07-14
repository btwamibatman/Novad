"""add document content and layout reviews

Revision ID: 20260714_0003
Revises: 20260709_0002
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260714_0003"
down_revision: Union[str, None] = "20260709_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def upgrade() -> None:
    document_columns = (
        ("content_review", sa.Text(), False, sa.text("''")),
        ("content_review_model", sa.String(length=100), True, None),
        ("content_review_error", sa.Text(), True, None),
        ("content_review_mode", sa.String(length=20), True, None),
        ("content_review_meta", sa.JSON(), False, sa.text("'{}'")),
        ("layout_review", sa.Text(), False, sa.text("''")),
        ("layout_review_model", sa.String(length=100), True, None),
        ("layout_review_error", sa.Text(), True, None),
        ("layout_review_meta", sa.JSON(), False, sa.text("'{}'")),
    )
    for name, column_type, nullable, server_default in document_columns:
        if not _column_exists("documents", name):
            op.add_column(
                "documents",
                sa.Column(
                    name,
                    column_type,
                    nullable=nullable,
                    server_default=server_default,
                ),
            )

    if not _column_exists("document_chunks", "extraction_method"):
        op.add_column(
            "document_chunks",
            sa.Column(
                "extraction_method",
                sa.String(length=20),
                nullable=False,
                server_default="unknown",
            ),
        )


def downgrade() -> None:
    if _column_exists("document_chunks", "extraction_method"):
        op.drop_column("document_chunks", "extraction_method")

    for column_name in (
        "layout_review_meta",
        "layout_review_error",
        "layout_review_model",
        "layout_review",
        "content_review_meta",
        "content_review_mode",
        "content_review_error",
        "content_review_model",
        "content_review",
    ):
        if _column_exists("documents", column_name):
            op.drop_column("documents", column_name)
