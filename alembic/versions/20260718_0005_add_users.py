"""add users

Revision ID: 20260718_0005
Revises: 20260714_0004
Create Date: 2026-07-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260718_0005"
down_revision: Union[str, None] = "20260714_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _table_exists("users"):
        return

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)


def downgrade() -> None:
    if not _table_exists("users"):
        return

    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
