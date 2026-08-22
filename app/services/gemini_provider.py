from __future__ import annotations

import re

from app.core.config import settings
from app.services.ai.provider import (
    AIDocument,
    AIGenerationResult,
    AIImage,
    AIProviderError,
    AIProviderNotConfigured,
    AIRemoteDocument,
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

    def upload_document(self, document: AIDocument) -> AIRemoteDocument:
        if not document.path.is_file():
            raise AIProviderError("Protected document is unavailable")
        if document.mime_type != "application/pdf":
            raise AIProviderError("Only protected PDF artifacts can be uploaded")
        if document.path.stat().st_size > settings.ai_max_pdf_bytes:
            raise AIProviderError(
                "Protected PDF exceeds the configured AI upload limit",
                code="pdf_too_large",
            )
        try:
            with self._client() as client:
                uploaded = client.files.upload(
                    file=str(document.path),
                    config=self._types.UploadFileConfig(
                        mime_type=document.mime_type,
                        display_name=document.display_name,
                    ),
                )
            return self._remote_document(uploaded)
        except AIProviderError:
            raise
        except Exception as error:
            raise self._provider_error(error, "Gemini document upload failed") from error

    def get_document(self, name: str) -> AIRemoteDocument:
        try:
            with self._client() as client:
                uploaded = client.files.get(name=name)
            return self._remote_document(uploaded)
        except Exception as error:
            raise self._provider_error(error, "Gemini document status failed") from error

    def delete_document(self, name: str) -> None:
        try:
            with self._client() as client:
                client.files.delete(name=name)
        except Exception as error:
            raise self._provider_error(error, "Gemini document deletion failed") from error

    def generate_document(
        self,
        prompt: str,
        document: AIDocument | AIRemoteDocument,
        *,
        max_output_tokens: int,
        response_schema: type | dict | None = None,
        temperature: float = 0.1,
        timeout_seconds: int | None = None,
    ) -> AIGenerationResult:
        if isinstance(document, AIRemoteDocument):
            if document.state != "ACTIVE":
                raise AIProviderError(
                    "Protected document is not ready at the AI provider",
                    retryable=document.state == "PROCESSING",
                    retry_after_seconds=2 if document.state == "PROCESSING" else None,
                )
            document_part = self._types.Part.from_uri(
                file_uri=document.uri,
                mime_type=document.mime_type,
            )
        else:
            if not document.path.is_file():
                raise AIProviderError("Protected document is unavailable")
            document_part = self._types.Part.from_bytes(
                data=document.path.read_bytes(),
                mime_type=document.mime_type,
            )
        contents = [document_part, self._types.Part.from_text(text=prompt)]
        return self._generate(
            contents=contents,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            response_schema=response_schema,
        )

    def _generate(
        self,
        *,
        contents,
        max_output_tokens: int,
        temperature: float,
        timeout_seconds: int | None,
        response_schema: type | dict | None = None,
    ) -> AIGenerationResult:
        request_timeout = timeout_seconds or settings.ai_request_timeout_seconds
        config = self._types.GenerateContentConfig(
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            thinking_config=self._types.ThinkingConfig(
                thinking_budget=settings.gemini_thinking_budget
            ),
            http_options=self._types.HttpOptions(timeout=request_timeout * 1000),
            response_mime_type=("application/json" if response_schema is not None else None),
            response_schema=response_schema,
        )
        try:
            with self._client() as client:
                response = client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
            text = (response.text or "").strip()
        except Exception as error:
            raise self._provider_error(error, "Gemini API request failed") from error

        if not text:
            finish_reasons = {
                str(getattr(getattr(candidate, "finish_reason", None), "value", "") or "")
                for candidate in (getattr(response, "candidates", None) or [])
            }
            if finish_reasons & {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"}:
                raise AIProviderError(
                    "AI blocked the response for safety reasons",
                    code="safety_block",
                )
            raise AIProviderError("AI returned an empty response", code="empty_response")
        usage = getattr(response, "usage_metadata", None)
        if usage is not None and hasattr(usage, "model_dump"):
            usage = usage.model_dump(mode="json", exclude_none=True)
        elif usage is not None and not isinstance(usage, dict):
            usage = None
        http_response = getattr(response, "sdk_http_response", None)
        headers = getattr(http_response, "headers", None) or {}
        request_id = headers.get("x-request-id") or headers.get("x-goog-request-id")
        return AIGenerationResult(
            text=text,
            model=self._model,
            usage=usage,
            request_id=request_id,
        )

    def _client(self):
        return self._genai.Client(
            api_key=self._api_key,
            http_options=self._types.HttpOptions(
                timeout=settings.ai_request_timeout_seconds * 1000
            ),
        )

    @staticmethod
    def _remote_document(uploaded) -> AIRemoteDocument:
        name = str(getattr(uploaded, "name", "") or "")
        uri = str(getattr(uploaded, "uri", "") or "")
        mime_type = str(getattr(uploaded, "mime_type", "") or "application/pdf")
        state_value = getattr(uploaded, "state", "STATE_UNSPECIFIED")
        state = str(getattr(state_value, "value", state_value)).split(".")[-1].upper()
        if not name or not uri:
            raise AIProviderError("Gemini returned invalid document metadata")
        return AIRemoteDocument(
            name=name,
            uri=uri,
            mime_type=mime_type,
            state=state,
            expires_at=getattr(uploaded, "expiration_time", None),
        )

    @staticmethod
    def _provider_error(error: Exception, message: str) -> AIProviderError:
        raw_code = getattr(error, "code", None)
        try:
            code = int(raw_code) if raw_code is not None else None
        except (TypeError, ValueError):
            code = None
        if code is None and "timeout" in type(error).__name__.casefold():
            code = 408
        detail = str(error)
        retryable = code in {408, 409, 429, 500, 502, 503, 504}
        retry_after = None
        retry_match = re.search(
            r"(?:retry(?:Delay| in)?['\"=: ]+)(\d+)(?:\.\d+)?s",
            detail,
            re.IGNORECASE,
        )
        if retry_match:
            retry_after = max(1, int(retry_match.group(1)))
        return AIProviderError(
            f"{message}{f' ({code})' if code is not None else ''}",
            code=code,
            retryable=retryable,
            retry_after_seconds=retry_after,
            provider_detail=detail,
        )
