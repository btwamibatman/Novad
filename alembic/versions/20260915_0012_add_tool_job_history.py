"""add persistent visibility for tool task history

Revision ID: 20260915_0012
Revises: 20260820_0011
"""

from alembic import op
import sqlalchemy as sa

revision = "20260915_0012"
down_revision = "20260820_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("tool_jobs")}
    if "hidden_from_history" in columns:
        return
    op.add_column(
        "tool_jobs",
        sa.Column("hidden_from_history", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("tool_jobs")}
    if "hidden_from_history" in columns:
        op.drop_column("tool_jobs", "hidden_from_history")
