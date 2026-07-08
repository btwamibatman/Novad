from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._utils import utc_now


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="uploaded", nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    detected_language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
