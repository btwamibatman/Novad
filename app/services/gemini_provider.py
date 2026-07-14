from __future__ import annotations

from app.core.config import settings
from app.services.ai_provider import (
    AIGenerationResult,
    AIImage,
    AIProviderError,
    AIProviderNotConfigured,
)


class GeminiProvider:
    def __init__(self) -> None:
        if not settings.gemini_api_key:
            raise AIProviderNotConfigured("GEMINI_API_KEY is not configured")

        try:
            from google import genai
            from google.genai import types
        except ImportError as error:
            raise AIProviderNotConfigured(
                "google-genai package is not installed"
            ) from error

        self._genai = genai
        self._types = types
        self._api_key = settings.gemini_api_key
        self._model = settings.gemini_model

    def generate_text(
        self,
        prompt: str,
        *,
        max_output_tokens: int,
        temperature: float = 0.2,
        timeout_seconds: int | None = None,
    ) -> AIGenerationResult:
        return self._generate(
            contents=prompt,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )

    def generate_multimodal(
        self,
        prompt: str,
        images: list[AIImage],
        *,
        max_output_tokens: int,
        temperature: float = 0.2,
        timeout_seconds: int | None = None,
    ) -> AIGenerationResult:
        if not images:
            raise AIProviderError("At least one image is required")

        contents = [self._types.Part.from_text(text=prompt)]
        contents.extend(
            self._types.Part.from_bytes(data=image.data, mime_type=image.mime_type)
            for image in images
        )
        return self._generate(
            contents=contents,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )

    def _generate(
        self,
        *,
        contents,
        max_output_tokens: int,
        temperature: float,
        timeout_seconds: int | None,
    ) -> AIGenerationResult:
        request_timeout = timeout_seconds or settings.ai_request_timeout_seconds
        config = self._types.GenerateContentConfig(
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            thinking_config=self._types.ThinkingConfig(
                thinking_budget=settings.gemini_thinking_budget
            ),
            http_options=self._types.HttpOptions(timeout=request_timeout * 1000),
        )
        try:
            with self._genai.Client(api_key=self._api_key) as client:
                response = client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
            text = (response.text or "").strip()
        except AIProviderError:
            raise
        except Exception as error:
            raise AIProviderError(f"Gemini API request failed: {error}") from error

        if not text:
            raise AIProviderError("AI returned an empty response")
        return AIGenerationResult(text=text, model=self._model)
