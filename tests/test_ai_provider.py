import pytest

from app.services import ai_provider
from app.services.ai_provider import AIImage
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
        def __init__(self, *, api_key):
            assert api_key == "test-key"
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
