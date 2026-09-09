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
    mode: Literal["question", "analysis", "suggestions"] = "question"

    @field_validator("question")
    @classmethod
    def strip_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Question is required")
        return stripped


class DocumentCitation(BaseModel):
    chunk_index: int = Field(ge=0)
    quote: str = Field(min_length=1, max_length=500)
    page: int | None = None
    text_matched: bool = False


class DocumentConclusion(BaseModel):
    observation: str = Field(min_length=1, max_length=1200)
    citations: list[DocumentCitation] = Field(default_factory=list, max_length=4)
    suggestion: str = Field(default="", max_length=1200)
    requires_review: bool = True


class GroundedAnswer(BaseModel):
    conclusions: list[DocumentConclusion] = Field(default_factory=list, max_length=12)
    limitations: list[str] = Field(default_factory=list, max_length=10)


class AIChatResponse(BaseModel):
    answer: str
    model: str
    truncated_context: bool
    privacy_applied: bool = False
    masked_entity_count: int = 0
    conclusions: list[DocumentConclusion] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    pages_reviewed: list[int] = Field(default_factory=list)
    retrieval_method: str = "bm25"
