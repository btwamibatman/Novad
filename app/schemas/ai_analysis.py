from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AIAnalysisTask = Literal["summary", "content_review", "layout_review"]
FindingCategory = Literal[
    "grammar",
    "style",
    "logic",
    "consistency",
    "ocr",
    "layout",
    "accessibility",
    "other",
]
FindingSeverity = Literal["critical", "high", "medium", "low"]
EvidenceBasis = Literal["native_text", "ocr", "vision"]


class AIAnalysisCoverage(BaseModel):
    pages_reviewed: list[int] = Field(default_factory=list)
    complete: bool = False
    limitations: list[str] = Field(default_factory=list, max_length=20)


class AIAnalysisFinding(BaseModel):
    category: FindingCategory
    severity: FindingSeverity
    page: int = Field(ge=1)
    evidence: str = Field(min_length=1, max_length=500)
    explanation: str = Field(min_length=1, max_length=1200)
    suggestion: str = Field(default="", max_length=1200)
    confidence: float = Field(ge=0, le=1)
    basis: EvidenceBasis
    requires_human_review: bool = False
    evidence_verified: bool = False


class AIAnalysisKeyPoint(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    page: int | None = Field(default=None, ge=1)
    evidence: str = Field(default="", max_length=500)
    evidence_verified: bool = False


class ProtectedDocumentAnalysis(BaseModel):
    task: AIAnalysisTask
    overview: str = Field(min_length=1, max_length=4000)
    verdict: str = Field(default="", max_length=2000)
    key_points: list[AIAnalysisKeyPoint] = Field(default_factory=list, max_length=20)
    findings: list[AIAnalysisFinding] = Field(default_factory=list, max_length=100)
    coverage: AIAnalysisCoverage


AIAnalysisJobStatus = Literal[
    "pending",
    "running",
    "retry_scheduled",
    "completed",
    "failed",
    "cancelled",
]
AIFileRetention = Literal["delete_after_analysis", "retain_48h"]
RemoteCleanupStatus = Literal[
    "not_applicable",
    "pending",
    "retained",
    "deleted",
    "failed",
]


class AIAnalysisJobCreate(BaseModel):
    artifact_id: int
    task: AIAnalysisTask = "content_review"
    retention: AIFileRetention = "delete_after_analysis"
    consent_to_external_processing: bool = False
    acknowledge_provider_data_terms: bool = False


class AIProviderInfo(BaseModel):
    provider: str
    model: str
    service_tier: Literal["unpaid", "paid"]
    max_remote_retention_hours: int = 48
    requires_verified_artifact: bool = True


class AIAnalysisJobRead(BaseModel):
    id: int
    artifact_id: int
    task: AIAnalysisTask
    status: AIAnalysisJobStatus
    stage: str
    progress: int
    worker_active: bool
    provider: str
    model: str | None
    retention: AIFileRetention
    result: dict
    usage: dict
    attempts: int
    not_before: datetime | None
    error_code: str | None
    public_error: str | None
    remote_file_present: bool
    remote_cleanup_status: RemoteCleanupStatus
    remote_cleanup_error: str | None
    provider_file_expires_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}
