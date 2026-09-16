import json

import pytest

from app.services.ai.provider import AIGenerationResult, AIProviderError


@pytest.fixture()
def processed_document(client, pdf_document_id, analysis_runner):
    client.post(f"/api/documents/{pdf_document_id}/analyze")
    analysis_runner()
    return pdf_document_id


def test_chat_returns_verified_evidence_without_embeddings(client, processed_document, monkeypatch):
    def unexpected_embed(*args, **kwargs):
        pytest.fail("A short document must not invoke the embedding model")

    def generate(self, prompt, **kwargs):
        assert "What language is this?" in prompt
        assert "Previous question" in prompt
        return AIGenerationResult(text=json.dumps({
            "conclusions": [{"observation": "The document contains English text.",
                             "citations": [{"chunk_index": 0, "quote": "English text"}]}],
            "limitations": [],
        }), model="test-local")

    monkeypatch.setattr("app.services.ollama_provider.OllamaProvider.embed", unexpected_embed)
    monkeypatch.setattr("app.services.ollama_provider.OllamaProvider.generate_structured", generate)
    response = client.post(f"/api/documents/{processed_document}/ask", json={
        "question": "What language is this?", "history": [{"role": "user", "content": "Previous question"}],
    })

    assert response.status_code == 200
    result = response.json()
    assert result["retrieval_method"] == "full_document"
    assert result["truncated_context"] is False
    assert result["conclusions"][0]["citations"][0]["text_matched"] is True
    assert result["conclusions"][0]["citations"][0]["page"] == 1


def test_chat_returns_provider_failure_to_the_client(client, processed_document, monkeypatch):
    def fail(*args, **kwargs):
        raise AIProviderError("Local AI is unavailable or timed out.")

    monkeypatch.setattr("app.services.ollama_provider.OllamaProvider.generate_structured", fail)
    response = client.post(f"/api/documents/{processed_document}/ask", json={"question": "What is here?"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Local AI is unavailable or timed out."
