"""add sessions

Revision ID: 20260707_0001
Revises:
Create Date: 2026-07-07
"""
from typing import Sequence, Union
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "20260707_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _column_nullable(table_name: str, column_name: str) -> bool:
    for column in sa.inspect(op.get_bind()).get_columns(table_name):
        if column["name"] == column_name:
            return bool(column["nullable"])
    return False


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def _foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    return any(
        foreign_key["name"] == constraint_name
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table_name)
    )


def upgrade() -> None:
    legacy_session_id = str(uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=120)

    if not _table_exists("sessions"):
        op.create_table(
            "sessions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("sessions", "ix_sessions_expires_at"):
        op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"], unique=False)

    if not _column_exists("documents", "session_id"):
        with op.batch_alter_table("documents") as batch_op:
            batch_op.add_column(sa.Column("session_id", sa.String(length=36), nullable=True))

    op.execute(
        sa.text(
            "INSERT INTO sessions (id, created_at, expires_at, last_seen_at) "
            "SELECT :id, :created_at, :expires_at, :last_seen_at "
            "WHERE EXISTS (SELECT 1 FROM documents WHERE session_id IS NULL)"
        ).bindparams(
            id=legacy_session_id,
            created_at=now,
            expires_at=expires_at,
            last_seen_at=now,
        )
    )
    op.execute(
        sa.text("UPDATE documents SET session_id = :session_id WHERE session_id IS NULL").bindparams(
            session_id=legacy_session_id
        )
    )

    if _column_nullable("documents", "session_id"):
        with op.batch_alter_table("documents") as batch_op:
            batch_op.alter_column("session_id", existing_type=sa.String(length=36), nullable=False)

    if not _index_exists("documents", "ix_documents_session_id"):
        op.create_index("ix_documents_session_id", "documents", ["session_id"], unique=False)

    if not _foreign_key_exists("documents", "fk_documents_session_id_sessions"):
        with op.batch_alter_table("documents") as batch_op:
            batch_op.create_foreign_key("fk_documents_session_id_sessions", "sessions", ["session_id"], ["id"])


def downgrade() -> None:
    if _column_exists("documents", "session_id"):
        with op.batch_alter_table("documents") as batch_op:
            if _foreign_key_exists("documents", "fk_documents_session_id_sessions"):
                batch_op.drop_constraint("fk_documents_session_id_sessions", type_="foreignkey")
            if _index_exists("documents", "ix_documents_session_id"):
                batch_op.drop_index("ix_documents_session_id")
            batch_op.drop_column("session_id")

    if _table_exists("sessions"):
        if _index_exists("sessions", "ix_sessions_expires_at"):
            op.drop_index("ix_sessions_expires_at", table_name="sessions")
        op.drop_table("sessions")
