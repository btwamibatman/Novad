from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.core.config import settings


class AIProviderError(RuntimeError):
    pass


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


def get_ai_provider() -> DocumentAIProvider:
    provider_name = settings.ai_provider.strip().lower()
    if provider_name == "gemini":
        from app.services.gemini_provider import GeminiProvider

        return GeminiProvider()
    raise AIProviderNotConfigured(
        f"AI provider '{settings.ai_provider}' is not configured"
    )
