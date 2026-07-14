import pytest

from app.services import ai_content_review
from app.services.ai_content_review import ReviewChunkData
from app.services.ai_provider import AIGenerationResult


class FakeProvider:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate_text(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return AIGenerationResult(
            text=f"review {len(self.prompts)}",
            model="test-model",
        )


def test_quick_review_marks_representative_sample(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(ai_content_review, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(
        ai_content_review.settings,
        "content_review_quick_max_chars",
        180,
    )
    chunks = [
        ReviewChunkData(index, index + 1, f"text-{index} " * 20, "ocr")
        for index in range(5)
    ]

    result = ai_content_review.review_document_content(chunks, "quick")

    assert result.text == "review 1"
    assert result.complete is False
    assert result.batch_count == 1
    assert "быстрая выборочная проверка" in provider.prompts[0]
    assert "extraction=ocr" in provider.prompts[0]


def test_thorough_review_uses_batches_and_reduce(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(ai_content_review, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(ai_content_review.settings, "content_review_batch_max_chars", 140)
    monkeypatch.setattr(ai_content_review.settings, "content_review_thorough_max_batches", 8)
    chunks = [
        ReviewChunkData(index, index + 1, "document text " * 7, "pypdf")
        for index in range(3)
    ]

    result = ai_content_review.review_document_content(chunks, "thorough")

    assert result.complete is True
    assert result.batch_count >= 2
    assert len(provider.prompts) == result.batch_count + 1
    assert "Промежуточные проверки" in provider.prompts[-1]
    assert result.text == f"review {len(provider.prompts)}"


def test_thorough_review_rejects_document_above_synchronous_limit(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(ai_content_review, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(ai_content_review.settings, "content_review_batch_max_chars", 80)
    monkeypatch.setattr(ai_content_review.settings, "content_review_thorough_max_batches", 1)
    chunks = [ReviewChunkData(0, 1, "long text " * 30, "pypdf")]

    with pytest.raises(ai_content_review.ContentReviewTooLarge, match="background-job"):
        ai_content_review.review_document_content(chunks, "thorough")

    assert provider.prompts == []
