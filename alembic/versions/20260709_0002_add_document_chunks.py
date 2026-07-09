"""add document chunks

Revision ID: 20260709_0002
Revises: 20260707_0001
Create Date: 2026-07-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260709_0002"
down_revision: Union[str, None] = "20260707_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    return any(
        column["name"] == column_name
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    )


def _index_exists(table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in sa.inspect(op.get_bind()).get_indexes(table_name))


def upgrade() -> None:
    if not _column_exists("documents", "language_distribution"):
        op.add_column(
            "documents",
            sa.Column(
                "language_distribution",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
        )

    if not _table_exists("document_chunks"):
        op.create_table(
            "document_chunks",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("document_id", sa.Integer(), nullable=False),
            sa.Column("page_number", sa.Integer(), nullable=True),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("detected_language", sa.String(length=20), nullable=True),
            sa.Column("word_count", sa.Integer(), nullable=False),
            sa.Column("char_count", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunks_document_chunk"),
        )
    if not _index_exists("document_chunks", "ix_document_chunks_id"):
        op.create_index("ix_document_chunks_id", "document_chunks", ["id"], unique=False)
    if not _index_exists("document_chunks", "ix_document_chunks_document_id"):
        op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"], unique=False)


def downgrade() -> None:
    if _table_exists("document_chunks"):
        if _index_exists("document_chunks", "ix_document_chunks_document_id"):
            op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
        if _index_exists("document_chunks", "ix_document_chunks_id"):
            op.drop_index("ix_document_chunks_id", table_name="document_chunks")
        op.drop_table("document_chunks")

    if _column_exists("documents", "language_distribution"):
        op.drop_column("documents", "language_distribution")
