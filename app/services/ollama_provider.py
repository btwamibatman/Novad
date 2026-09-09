from __future__ import annotations

import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, HTTPRedirectHandler, Request, build_opener

from app.core.config import settings
from app.services.ai.provider import AIGenerationResult, AIImage, AIProviderError


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _generation_schema(value):
    # Ollama's grammar compiler can reject bounded nested arrays/numbers. Keep
    # structure and enums in the sampler; Pydantic enforces all bounds afterwards.
    if isinstance(value, list):
        return [_generation_schema(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _generation_schema(item) for key, item in value.items()
            if key not in {"default", "title", "minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems"}
        }
    return value


class OllamaProvider:
    """Local inference only: no proxies, redirects, cloud fallback or file uploads."""

    def _post(self, endpoint: str, payload: dict, timeout: int | None = None) -> dict:
        request = Request(
            f"{settings.ollama_base_url.rstrip('/')}/api/{endpoint}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with build_opener(ProxyHandler({}), _NoRedirect()).open(
                request, timeout=timeout or settings.ollama_timeout_seconds
            ) as response:
                result = json.load(response)
        except HTTPError as error:
            detail = error.read(2000).decode("utf-8", errors="replace")
            raise AIProviderError(
                "Local AI request failed. Check the installed model and server settings.",
                code=error.code, retryable=error.code in {429, 500, 502, 503, 504},
                provider_detail=detail,
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise AIProviderError(
                "Local AI is unavailable or timed out. No data was sent to an external service.",
                code="local_unavailable", retryable=True,
            ) from error
        except (ValueError, UnicodeError) as error:
            raise AIProviderError("Local AI returned an invalid response") from error
        if not isinstance(result, dict) or result.get("error"):
            raise AIProviderError("Local AI returned an error")
        return result

    def generate_text(self, prompt, *, max_output_tokens, temperature=0.2,
                      timeout_seconds=None) -> AIGenerationResult:
        return self.generate_structured(
            prompt, max_output_tokens=max_output_tokens, temperature=temperature,
            timeout_seconds=timeout_seconds,
        )

    def generate_multimodal(self, prompt, images: list[AIImage], *, max_output_tokens,
                            temperature=0.2, timeout_seconds=None) -> AIGenerationResult:
        if not images:
            raise AIProviderError("At least one image is required")
        return self.generate_structured(
            prompt, images=images, max_output_tokens=max_output_tokens,
            temperature=temperature, timeout_seconds=timeout_seconds,
        )

    def generate_structured(self, prompt, *, max_output_tokens, response_schema=None,
                            images=(), temperature=0.1, timeout_seconds=None):
        message = {"role": "user", "content": prompt}
        if images:
            message["images"] = [base64.b64encode(image.data).decode("ascii") for image in images]
        payload = {
            "model": settings.ollama_model, "messages": [message],
            "stream": False, "think": False, "keep_alive": "5m",
            "options": {"temperature": temperature, "num_predict": max_output_tokens,
                        "num_ctx": settings.ollama_context_length},
        }
        if response_schema is not None:
            payload["format"] = _generation_schema(response_schema.model_json_schema())
        # Local cold starts need a different timeout from the cloud chat endpoint.
        result = self._post("chat", payload, settings.ollama_timeout_seconds)
        content = result.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip() or not result.get("done"):
            raise AIProviderError("Local AI returned an empty or incomplete answer")
        if result.get("done_reason") == "length":
            raise AIProviderError("Local AI output exceeded the token limit; narrow the request")
        return AIGenerationResult(
            text=content.strip(), model=result.get("model", settings.ollama_model),
            usage={key: result[key] for key in ("prompt_eval_count", "eval_count", "total_duration") if key in result},
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = self._post("embed", {
            "model": settings.ollama_embedding_model, "input": texts,
            "truncate": False, "keep_alive": "0",
        })
        vectors = result.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise AIProviderError("Local embeddings response has an invalid size")
        import math

        dimension = len(vectors[0]) if vectors and isinstance(vectors[0], list) else 0
        if not dimension or any(
            not isinstance(v, list) or len(v) != dimension
            or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in v)
            or not any(v) for v in vectors
        ):
            raise AIProviderError("Local embeddings response is invalid")
        return vectors
