"""add document extraction quality metadata

Revision ID: 20260714_0004
Revises: 20260714_0003
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260714_0004"
down_revision: Union[str, None] = "20260714_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def upgrade() -> None:
    if not _column_exists("documents", "extraction_quality"):
        op.add_column(
            "documents",
            sa.Column(
                "extraction_quality",
                sa.String(length=20),
                nullable=False,
                server_default="unknown",
            ),
        )
    if not _column_exists("documents", "extraction_quality_meta"):
        op.add_column(
            "documents",
            sa.Column(
                "extraction_quality_meta",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )


def downgrade() -> None:
    if _column_exists("documents", "extraction_quality_meta"):
        op.drop_column("documents", "extraction_quality_meta")
    if _column_exists("documents", "extraction_quality"):
        op.drop_column("documents", "extraction_quality")
