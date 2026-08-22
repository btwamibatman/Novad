import pytest
from pathlib import Path

from app.services.ai import provider as ai_provider
from app.services.ai.provider import AIDocument, AIImage, AIRemoteDocument
from app.services.gemini_provider import GeminiProvider


def test_unknown_ai_provider_is_rejected(monkeypatch):
    monkeypatch.setattr(ai_provider.settings, "ai_provider", "local")

    with pytest.raises(ai_provider.AIProviderNotConfigured, match="local"):
        ai_provider.get_ai_provider()


def test_gemini_provider_uses_current_sdk_for_multimodal_request(monkeypatch):
    monkeypatch.setattr(ai_provider.settings, "gemini_api_key", "test-key")
    provider = GeminiProvider()
    captured = {}

    class FakeModels:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return type("Response", (), {"text": "Visual review"})()

    class FakeClient:
        def __init__(self, *, api_key, http_options):
            assert api_key == "test-key"
            assert http_options.timeout == 45000
            self.models = FakeModels()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(provider._genai, "Client", FakeClient)

    result = provider.generate_multimodal(
        "Review visual layout",
        [AIImage(b"png-data")],
        max_output_tokens=100,
        timeout_seconds=12,
    )

    assert result.text == "Visual review"
    assert captured["model"] == provider._model
    assert captured["config"].http_options.timeout == 12000
    assert captured["config"].thinking_config.thinking_budget == 0
    assert captured["contents"][1].inline_data.mime_type == "image/png"


def test_gemini_provider_uploads_and_reuses_protected_pdf(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_provider.settings, "gemini_api_key", "test-key")
    provider = GeminiProvider()
    source = tmp_path / "protected.pdf"
    source.write_bytes(b"%PDF-protected")
    captured = {}

    uploaded = type(
        "Uploaded",
        (),
        {
            "name": "files/protected-1",
            "uri": "https://provider/files/protected-1",
            "mime_type": "application/pdf",
            "state": "ACTIVE",
            "expiration_time": None,
        },
    )()

    class FakeFiles:
        def upload(self, **kwargs):
            captured["upload"] = kwargs
            return uploaded

        def get(self, **kwargs):
            return uploaded

        def delete(self, **kwargs):
            captured["delete"] = kwargs

    class FakeModels:
        def generate_content(self, **kwargs):
            captured["generate"] = kwargs
            return type("Response", (), {"text": '{"verdict":"ok"}'})()

    class FakeClient:
        def __init__(self, *, api_key, http_options):
            assert api_key == "test-key"
            assert http_options.timeout == 45000
            self.files = FakeFiles()
            self.models = FakeModels()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(provider._genai, "Client", FakeClient)

    remote = provider.upload_document(AIDocument(source))
    result = provider.generate_document(
        "Review protected PDF",
        remote,
        max_output_tokens=100,
        response_schema={"type": "object"},
    )
    provider.delete_document(remote.name)

    assert remote.state == "ACTIVE"
    assert Path(captured["upload"]["file"]) == source
    assert captured["upload"]["config"].display_name == "protected-document.pdf"
    assert captured["generate"]["contents"][0].file_data.file_uri == remote.uri
    assert captured["generate"]["config"].response_mime_type == "application/json"
    assert result.text == '{"verdict":"ok"}'
    assert captured["delete"] == {"name": "files/protected-1"}


def test_gemini_provider_marks_quota_error_retryable(monkeypatch):
    monkeypatch.setattr(ai_provider.settings, "gemini_api_key", "test-key")
    provider = GeminiProvider()

    class QuotaError(Exception):
        code = 429

        def __str__(self):
            return "RESOURCE_EXHAUSTED retry in 56.3s"

    class FakeModels:
        def generate_content(self, **kwargs):
            raise QuotaError()

    class FakeClient:
        def __init__(self, *, api_key, http_options):
            assert http_options.timeout == 45000
            self.models = FakeModels()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(provider._genai, "Client", FakeClient)

    with pytest.raises(ai_provider.AIProviderError) as captured:
        provider.generate_text("prompt", max_output_tokens=10)

    assert captured.value.code == 429
    assert captured.value.retryable is True
    assert captured.value.retry_after_seconds == 56


def test_gemini_provider_rejects_oversized_pdf_before_upload(monkeypatch, tmp_path):
    monkeypatch.setattr(ai_provider.settings, "gemini_api_key", "test-key")
    monkeypatch.setattr(ai_provider.settings, "ai_max_pdf_bytes", 4)
    provider = GeminiProvider()
    source = tmp_path / "protected.pdf"
    source.write_bytes(b"%PDF-too-large")

    with pytest.raises(ai_provider.AIProviderError) as captured:
        provider.upload_document(AIDocument(source))

    assert captured.value.code == "pdf_too_large"
    assert captured.value.retryable is False
