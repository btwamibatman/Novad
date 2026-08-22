from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models._utils import utc_now


class AIAnalysisJob(Base):
    __tablename__ = "ai_analysis_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    artifact_id: Mapped[int] = mapped_column(
        ForeignKey("document_artifacts.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    task: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), index=True, default="pending", nullable=False
    )
    stage: Mapped[str] = mapped_column(String(40), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    worker_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(30), default="protected-v1")
    schema_version: Mapped[str] = mapped_column(String(30), default="analysis-v1")
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True
    )
    retention: Mapped[str] = mapped_column(
        String(30), default="delete_after_analysis", nullable=False
    )
    consent_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    usage: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    provider_file_name: Mapped[str | None] = mapped_column(String(255))
    provider_file_uri: Mapped[str | None] = mapped_column(Text)
    provider_file_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    provider_file_processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    remote_cleanup_status: Mapped[str] = mapped_column(
        String(30), default="not_applicable", nullable=False
    )
    remote_cleanup_error: Mapped[str | None] = mapped_column(Text)
    provider_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(50))
    public_error: Mapped[str | None] = mapped_column(Text)
    private_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def remote_file_present(self) -> bool:
        return bool(self.provider_file_name)
