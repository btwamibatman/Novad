from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

DocumentStatus = Literal["uploaded", "processed", "failed"]


class DocumentRead(BaseModel):
    id: int
    session_id: str
    filename: str
    content_type: str
    size_bytes: int
    status: DocumentStatus
    extracted_text: str
    detected_language: str | None
    word_count: int
    char_count: int
    error_message: str | None
    ai_summary: str
    ai_model: str | None
    ai_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
