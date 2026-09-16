from types import SimpleNamespace
from unittest.mock import Mock

from app.services.documents import retrieval


def test_short_document_keeps_all_evidence_without_embedding_requests(monkeypatch):
    provider = Mock()
    monkeypatch.setattr(retrieval, "OllamaProvider", provider)
    monkeypatch.setattr(retrieval.settings, "semantic_search_enabled", True)
    chunks = [SimpleNamespace(chunk_index=i, text=f"Evidence {i}") for i in [4, 2, 0, 3, 1]]

    result = retrieval.retrieve(chunks, "What was completed?")

    assert result.chunks == sorted(chunks, key=lambda c: c.chunk_index)
    assert result.method == "full_document"
    assert result.limitations == []
    provider.assert_not_called()


def test_long_document_still_selects_relevant_context(monkeypatch):
    monkeypatch.setattr(retrieval.settings, "semantic_search_enabled", False)
    chunks = [SimpleNamespace(chunk_index=i, text="unrelated material") for i in range(6)]
    chunks[-1].text = "The completion deadline is September"

    result = retrieval.retrieve(chunks, "completion deadline", top_k=2)

    assert len(result.chunks) == 2
    assert chunks[-1] in result.chunks
    assert result.method == "bm25"
