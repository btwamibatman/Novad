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


def test_review_removes_storage_overlap_from_consecutive_page_chunks(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(ai_content_review, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(
        ai_content_review.settings,
        "content_review_quick_max_chars",
        1000,
    )
    overlap = "shared boundary text long enough"
    chunks = [
        ReviewChunkData(0, 1, f"first section {overlap}", "pypdf"),
        ReviewChunkData(1, 1, f"{overlap} second section", "pypdf"),
    ]

    result = ai_content_review.review_document_content(chunks, "quick")

    assert provider.prompts[0].count(overlap) == 1
    assert result.total_chars == len(f"first section {overlap}") + len(
        "second section"
    )


def test_thorough_review_preserves_chunk_attribution_when_splitting(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(ai_content_review, "get_ai_provider", lambda: provider)
    monkeypatch.setattr(
        ai_content_review.settings,
        "content_review_batch_max_chars",
        140,
    )
    monkeypatch.setattr(
        ai_content_review.settings,
        "content_review_thorough_max_batches",
        20,
    )
    chunks = [
        ReviewChunkData(7, 3, "readable words " * 30, "ocr", "low", 61.0, 2)
    ]

    result = ai_content_review.review_document_content(chunks, "thorough")

    batch_prompts = provider.prompts[:-1]
    assert result.batch_count == len(batch_prompts)
    assert result.batch_count > 1
    assert all("[chunk=7" in prompt for prompt in batch_prompts)
    assert all("readable" in prompt and "words" in prompt for prompt in batch_prompts)
