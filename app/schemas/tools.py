from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CompressionMode = Literal["low", "recommended", "extreme"]
ToolJobStatus = Literal["pending", "running", "review", "completed", "failed"]
RedactionMode = Literal["black", "pseudonymize"]
RedactionCategory = Literal["personal", "financial", "visual", "service"]


class CompressionRequest(BaseModel):
    document_id: int
    mode: CompressionMode = "recommended"


class PdfToWordRequest(BaseModel):
    document_id: int


class RedactionPreviewRequest(BaseModel):
    document_id: int
    categories: list[RedactionCategory] = Field(
        default_factory=lambda: ["personal", "financial"]
    )


class RedactionRect(BaseModel):
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    width: float = Field(gt=0, le=100)
    height: float = Field(gt=0, le=100)


class RedactionArea(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    page: int = Field(ge=1)
    rect: RedactionRect


class RedactionApplyRequest(BaseModel):
    finding_ids: list[str] = Field(default_factory=list)
    areas: list[RedactionArea] = Field(default_factory=list, max_length=500)
    mode: RedactionMode = "black"


class ToolJobRead(BaseModel):
    id: int
    source_document_id: int | None
    kind: str
    status: ToolJobStatus
    stage: str
    progress: int
    source_filename: str
    source_content_type: str
    options: dict = Field(default_factory=dict)
    findings: list = Field(default_factory=list)
    result_filename: str | None
    result_content_type: str | None
    result_size_bytes: int | None
    result_meta: dict = Field(default_factory=dict)
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
