"""add authenticated sessions and document ownership

Revision ID: 20260718_0006
Revises: 20260718_0005
Create Date: 2026-07-18
"""
from datetime import datetime, timedelta, timezone
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "20260718_0006"
down_revision: Union[str, None] = "20260718_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _column_nullable(table_name: str, column_name: str) -> bool:
    return next(
        bool(column["nullable"])
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
        if column["name"] == column_name
    )


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(
        index["name"] == index_name
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    )


def _foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    return any(
        foreign_key["name"] == constraint_name
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table_name)
    )


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch_op:
        if not _column_exists("sessions", "user_id"):
            batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        if not _column_exists("sessions", "token_hash"):
            batch_op.add_column(sa.Column("token_hash", sa.String(length=64), nullable=True))

    if not _foreign_key_exists("sessions", "fk_sessions_user_id_users"):
        with op.batch_alter_table("sessions") as batch_op:
            batch_op.create_foreign_key(
                "fk_sessions_user_id_users",
                "users",
                ["user_id"],
                ["id"],
                ondelete="CASCADE",
            )
    if not _index_exists("sessions", "ix_sessions_user_id"):
        op.create_index("ix_sessions_user_id", "sessions", ["user_id"], unique=False)
    if not _index_exists("sessions", "ix_sessions_token_hash"):
        op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True)

    if not _column_exists("documents", "user_id"):
        with op.batch_alter_table("documents") as batch_op:
            batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
    if not _foreign_key_exists("documents", "fk_documents_user_id_users"):
        with op.batch_alter_table("documents") as batch_op:
            batch_op.create_foreign_key(
                "fk_documents_user_id_users",
                "users",
                ["user_id"],
                ["id"],
                ondelete="CASCADE",
            )
    if not _index_exists("documents", "ix_documents_user_id"):
        op.create_index("ix_documents_user_id", "documents", ["user_id"], unique=False)

    if not _column_nullable("documents", "session_id"):
        with op.batch_alter_table("documents") as batch_op:
            batch_op.alter_column(
                "session_id",
                existing_type=sa.String(length=36),
                nullable=True,
            )


def downgrade() -> None:
    null_session_count = op.get_bind().scalar(
        sa.text("SELECT COUNT(*) FROM documents WHERE session_id IS NULL")
    )
    if null_session_count:
        legacy_session_id = str(uuid4())
        now = datetime.now(timezone.utc)
        op.execute(
            sa.text(
                "INSERT INTO sessions "
                "(id, user_id, token_hash, created_at, expires_at, last_seen_at) "
                "VALUES (:id, NULL, NULL, :created_at, :expires_at, :last_seen_at)"
            ).bindparams(
                id=legacy_session_id,
                created_at=now,
                expires_at=now + timedelta(minutes=120),
                last_seen_at=now,
            )
        )
        op.execute(
            sa.text(
                "UPDATE documents SET session_id = :session_id WHERE session_id IS NULL"
            ).bindparams(session_id=legacy_session_id)
        )

    if _index_exists("documents", "ix_documents_user_id"):
        op.drop_index("ix_documents_user_id", table_name="documents")
    with op.batch_alter_table("documents") as batch_op:
        if _foreign_key_exists("documents", "fk_documents_user_id_users"):
            batch_op.drop_constraint("fk_documents_user_id_users", type_="foreignkey")
        if _column_exists("documents", "user_id"):
            batch_op.drop_column("user_id")
        batch_op.alter_column(
            "session_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )

    if _index_exists("sessions", "ix_sessions_token_hash"):
        op.drop_index("ix_sessions_token_hash", table_name="sessions")
    if _index_exists("sessions", "ix_sessions_user_id"):
        op.drop_index("ix_sessions_user_id", table_name="sessions")
    with op.batch_alter_table("sessions") as batch_op:
        if _foreign_key_exists("sessions", "fk_sessions_user_id_users"):
            batch_op.drop_constraint("fk_sessions_user_id_users", type_="foreignkey")
        if _column_exists("sessions", "token_hash"):
            batch_op.drop_column("token_hash")
        if _column_exists("sessions", "user_id"):
            batch_op.drop_column("user_id")
