from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocumentStatus = Literal["uploaded", "processed", "failed"]
DocumentReviewMode = Literal["quick", "thorough"]
DocumentExtractionQuality = Literal["unknown", "high", "medium", "low"]


class DocumentReviewRequest(BaseModel):
    mode: DocumentReviewMode = "quick"


class DocumentRead(BaseModel):
    id: int
    user_id: int
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    extracted_text: str
    extraction_quality: DocumentExtractionQuality
    extraction_quality_meta: dict = Field(default_factory=dict)
    detected_language: str | None
    language_distribution: dict[str, float] = Field(default_factory=dict)
    word_count: int
    char_count: int
    error_message: str | None
    ai_summary: str
    ai_model: str | None
    ai_error: str | None
    content_review: str
    content_review_model: str | None
    content_review_error: str | None
    content_review_mode: DocumentReviewMode | None
    content_review_meta: dict = Field(default_factory=dict)
    layout_review: str
    layout_review_model: str | None
    layout_review_error: str | None
    layout_review_meta: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
