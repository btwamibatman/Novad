import pytest

from app.services.ai import summary as ai_summary
from app.services.ai.content_review import ContentReviewResult
from app.services.ai import content_review as ai_content_review
from app.services.pii_masking import (
    PIIMaskingError,
    PIIMaskingSession,
    PIIMaskingUnavailable,
    PIISpan,
    RegexPIIRecognizer,
)


class ExactRecognizer:
    def __init__(self, values: list[tuple[str, str]]) -> None:
        self.values = values

    def find(self, text: str) -> list[PIISpan]:
        spans = []
        for category, value in self.values:
            start = text.find(value)
            while start >= 0:
                spans.append(PIISpan(start, start + len(value), category))
                start = text.find(value, start + len(value))
        return spans


def test_masking_uses_stable_tokens_and_restores_values():
    session = PIIMaskingSession(
        [
            ExactRecognizer(
                [
                    ("PERSON", "Иванов И.И."),
                    ("DOC_ID", "4521-К"),
                    ("AMOUNT", "3.2 млн руб"),
                ]
            )
        ],
        enabled=True,
    )

    first = session.mask(
        "Иванов И.И., договор 4521-К на 3.2 млн руб. Иванов И.И. отвечает."
    )
    second = session.mask("Что сделал Иванов И.И. по договору 4521-К?")

    assert first == (
        "[PERSON_1], договор [DOC_ID_1] на [AMOUNT_1]. "
        "[PERSON_1] отвечает."
    )
    assert second == "Что сделал [PERSON_1] по договору [DOC_ID_1]?"
    assert session.restore(first) == (
        "Иванов И.И., договор 4521-К на 3.2 млн руб. Иванов И.И. отвечает."
    )
    assert session.meta.entity_count == 3
    assert session.meta.categories == {"AMOUNT": 1, "DOC_ID": 1, "PERSON": 1}


def test_regex_recognizer_masks_kazakhstan_identifiers_and_contacts():
    session = PIIMaskingSession([RegexPIIRecognizer()], enabled=True)

    masked = session.mask(
        "ИИН 990101123456, email user@example.kz, телефон +7 701 123 45 67, "
        "сумма 3 200 000 KZT."
    )

    assert "990101123456" not in masked
    assert "user@example.kz" not in masked
    assert "+7 701 123 45 67" not in masked
    assert "3 200 000 KZT" not in masked
    assert session.restore(masked).startswith("ИИН 990101123456")


def test_restore_rejects_unknown_placeholder():
    session = PIIMaskingSession(
        [ExactRecognizer([("PERSON", "Иванов")])],
        enabled=True,
    )
    session.mask("Иванов")

    with pytest.raises(PIIMaskingError, match="unknown privacy placeholder"):
        session.restore("Ответ содержит [PERSON_999]")

    with pytest.raises(PIIMaskingError, match="unknown privacy placeholder"):
        session.restore("Ответ изменил placeholder на [person-1]")


def test_summary_route_masks_prompt_and_restores_response(
    client,
    pdf_document_id,
    analysis_runner,
    monkeypatch,
):
    client.post(f"/api/documents/{pdf_document_id}/analyze")
    analysis_runner()
    session = PIIMaskingSession(
        [ExactRecognizer([("PERSON", "English text")])],
        enabled=True,
    )
    monkeypatch.setattr(
        "app.api.routes.documents.PIIMaskingSession",
        lambda: session,
    )

    def fake_summary(chunks, extraction_quality):
        assert all("English text" not in chunk for chunk in chunks)
        assert any("[PERSON_1]" in chunk for chunk in chunks)
        return "Summary about [PERSON_1].", "test-model"

    monkeypatch.setattr(ai_summary, "summarize_chunks", fake_summary)

    response = client.post(f"/api/documents/{pdf_document_id}/summarize")

    assert response.status_code == 200
    assert response.json()["ai_summary"] == "Summary about English text."
    assert response.json()["ai_summary_meta"]["privacy"]["entity_count"] == 1


def test_summary_route_fails_closed_when_local_recognizer_is_unavailable(
    client,
    pdf_document_id,
    analysis_runner,
    monkeypatch,
):
    client.post(f"/api/documents/{pdf_document_id}/analyze")
    analysis_runner()

    class UnavailableRecognizer:
        def find(self, text):
            raise PIIMaskingUnavailable("Local PII model is unavailable")

    monkeypatch.setattr(
        "app.api.routes.documents.PIIMaskingSession",
        lambda: PIIMaskingSession([UnavailableRecognizer()], enabled=True),
    )
    called = False

    def should_not_call_provider(chunks, extraction_quality):
        nonlocal called
        called = True
        return "unsafe", "test-model"

    monkeypatch.setattr(ai_summary, "summarize_chunks", should_not_call_provider)

    response = client.post(f"/api/documents/{pdf_document_id}/summarize")

    assert response.status_code == 503
    assert called is False


def test_content_review_masks_chunks_and_restores_provider_output(
    client,
    pdf_document_id,
    analysis_runner,
    monkeypatch,
):
    client.post(f"/api/documents/{pdf_document_id}/analyze")
    analysis_runner()
    session = PIIMaskingSession(
        [ExactRecognizer([("PERSON", "English text")])],
        enabled=True,
    )
    monkeypatch.setattr(
        "app.api.routes.documents.PIIMaskingSession",
        lambda: session,
    )

    def fake_review(chunks, mode):
        assert all("English text" not in chunk.text for chunk in chunks)
        assert any("[PERSON_1]" in chunk.text for chunk in chunks)
        return ContentReviewResult(
            text="Review of [PERSON_1].",
            model="test-model",
            mode=mode,
            total_chars=100,
            reviewed_chars=100,
            batch_count=1,
            complete=True,
        )

    monkeypatch.setattr(
        ai_content_review,
        "review_document_content",
        fake_review,
    )

    response = client.post(
        f"/api/documents/{pdf_document_id}/content-review",
        json={"mode": "quick"},
    )

    assert response.status_code == 200
    assert response.json()["content_review"] == "Review of English text."
    assert response.json()["content_review_meta"]["privacy"]["entity_count"] == 1


def test_ask_masks_context_question_and_history_in_one_session(
    client,
    pdf_document_id,
    analysis_runner,
    monkeypatch,
):
    client.post(f"/api/documents/{pdf_document_id}/analyze")
    analysis_runner()
    session = PIIMaskingSession(
        [
            ExactRecognizer(
                [
                    ("PERSON", "English text"),
                    ("PERSON", "Иван Иванов"),
                    ("DOC_ID", "4521-К"),
                ]
            )
        ],
        enabled=True,
    )
    monkeypatch.setattr(
        "app.api.routes.documents.PIIMaskingSession",
        lambda: session,
    )

    def fake_answer(context, question, history, extraction_quality):
        assert "English text" not in context
        assert "Иван Иванов" not in question
        assert "4521-К" not in history[0]["content"]
        assert "[PERSON_1]" in context
        assert "[PERSON_2]" in question
        assert "[DOC_ID_1]" in history[0]["content"]
        return "Ответ для [PERSON_2] по [DOC_ID_1].", "test-model", False

    monkeypatch.setattr(
        ai_summary,
        "answer_document_question",
        fake_answer,
    )

    response = client.post(
        f"/api/documents/{pdf_document_id}/ask",
        json={
            "question": "Что сделал Иван Иванов?",
            "history": [
                {"role": "user", "content": "Ранее обсуждали договор 4521-К"}
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Ответ для Иван Иванов по 4521-К."
    assert response.json()["privacy_applied"] is True
    assert response.json()["masked_entity_count"] == 3
