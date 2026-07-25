from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AIChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1500)

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Message content is required")
        return stripped


class AIChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[AIChatMessage] = Field(default_factory=list, max_length=12)

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Question is required")
        return stripped


class AIChatResponse(BaseModel):
    answer: str
    model: str
    truncated_context: bool
    privacy_applied: bool = False
    masked_entity_count: int = 0
