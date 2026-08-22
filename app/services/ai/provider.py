from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from app.core.config import settings


class AIProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: int | str | None = None,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
        provider_detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.provider_detail = provider_detail


class AIProviderNotConfigured(AIProviderError):
    pass


@dataclass(frozen=True)
class AIImage:
    data: bytes
    mime_type: str = "image/png"


@dataclass(frozen=True)
class AIGenerationResult:
    text: str
    model: str
    usage: dict | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class AIDocument:
    path: Path
    mime_type: str = "application/pdf"
    display_name: str = "protected-document.pdf"


@dataclass(frozen=True)
class AIRemoteDocument:
    name: str
    uri: str
    mime_type: str
    state: str
    expires_at: datetime | None = None


class DocumentAIProvider(Protocol):
    def generate_text(
        self,
        prompt: str,
        *,
        max_output_tokens: int,
        temperature: float = 0.2,
        timeout_seconds: int | None = None,
    ) -> AIGenerationResult: ...

    def generate_multimodal(
        self,
        prompt: str,
        images: list[AIImage],
        *,
        max_output_tokens: int,
        temperature: float = 0.2,
        timeout_seconds: int | None = None,
    ) -> AIGenerationResult: ...

    def upload_document(self, document: AIDocument) -> AIRemoteDocument: ...

    def get_document(self, name: str) -> AIRemoteDocument: ...

    def delete_document(self, name: str) -> None: ...

    def generate_document(
        self,
        prompt: str,
        document: AIDocument | AIRemoteDocument,
        *,
        max_output_tokens: int,
        response_schema: type | dict | None = None,
        temperature: float = 0.1,
        timeout_seconds: int | None = None,
    ) -> AIGenerationResult: ...


def get_ai_provider() -> DocumentAIProvider:
    provider_name = settings.ai_provider.strip().lower()
    if provider_name == "gemini":
        from app.services.gemini_provider import GeminiProvider

        return GeminiProvider()
    raise AIProviderNotConfigured(
        f"AI provider '{settings.ai_provider}' is not configured"
    )
