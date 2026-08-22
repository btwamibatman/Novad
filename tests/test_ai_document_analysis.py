import json

import pytest

from app.schemas.ai_analysis import ProtectedDocumentAnalysis
from app.services.ai.document_analysis import (
    ProtectedDocumentOutputError,
    analyze_protected_document,
)
from app.services.ai.provider import AIGenerationResult, AIRemoteDocument


REMOTE = AIRemoteDocument(
    name="files/protected",
    uri="https://provider/files/protected",
    mime_type="application/pdf",
    state="ACTIVE",
)


class FakeProvider:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.schema = None

    def generate_document(self, prompt, document, **kwargs):
        assert "защищённую копию" in prompt
        assert document is REMOTE
        self.schema = kwargs["response_schema"]
        return AIGenerationResult(
            json.dumps(self.payload),
            "test-model",
            {"total": 10},
            request_id="request-123",
        )


def _payload(page: int = 1) -> dict:
    return {
        "task": "content_review",
        "overview": "Документ требует небольшой правки.",
        "verdict": "Исправить формулировку.",
        "key_points": [
            {"text": "В документе есть срок", "page": 1, "evidence": "срок проекта 10 дней"}
        ],
        "findings": [
            {
                "category": "style",
                "severity": "medium",
                "page": page,
                "evidence": "срок проекта 10 дней",
                "explanation": "Формулировку можно уточнить.",
                "suggestion": "Указать даты.",
                "confidence": 0.9,
                "basis": "native_text",
            }
        ],
        "coverage": {"pages_reviewed": [1], "complete": True, "limitations": []},
    }


def test_structured_analysis_validates_page_evidence():
    provider = FakeProvider(_payload())

    result, model, usage = analyze_protected_document(
        provider,
        REMOTE,
        task="content_review",
        page_texts=["План: срок проекта 10 дней."],
    )

    assert provider.schema is ProtectedDocumentAnalysis
    assert result.findings[0].evidence_verified is True
    assert result.findings[0].requires_human_review is False
    assert result.findings[0].basis == "ocr"
    assert result.key_points[0].evidence_verified is True
    assert model == "test-model"
    assert usage == {"total": 10, "request_id": "request-123"}


def test_unmatched_text_evidence_requires_manual_review():
    result, _, _ = analyze_protected_document(
        FakeProvider(_payload()),
        REMOTE,
        task="content_review",
        page_texts=["Другой текст."],
    )

    assert result.findings[0].evidence_verified is False
    assert result.findings[0].requires_human_review is True


def test_missing_local_ocr_is_exposed_as_incomplete_coverage():
    result, _, _ = analyze_protected_document(
        FakeProvider(_payload()),
        REMOTE,
        task="content_review",
        page_texts=[""],
    )

    assert result.coverage.complete is False
    assert result.coverage.limitations == [
        "Local OCR evidence verification unavailable on pages: 1"
    ]


def test_out_of_range_page_is_rejected():
    with pytest.raises(ProtectedDocumentOutputError, match="invalid finding page"):
        analyze_protected_document(
            FakeProvider(_payload(page=2)),
            REMOTE,
            task="content_review",
            page_texts=["Одна страница."],
        )


def test_complete_coverage_must_include_every_page():
    with pytest.raises(ProtectedDocumentOutputError, match="incomplete page coverage"):
        analyze_protected_document(
            FakeProvider(_payload()),
            REMOTE,
            task="content_review",
            page_texts=["Первая страница.", "Вторая страница."],
        )


def test_vision_evidence_is_not_claimed_as_locally_verified():
    payload = _payload()
    payload["findings"][0]["basis"] = "vision"

    result, _, _ = analyze_protected_document(
        FakeProvider(payload),
        REMOTE,
        task="content_review",
        page_texts=["План: срок проекта 10 дней."],
    )

    assert result.findings[0].evidence_verified is False
    assert result.findings[0].requires_human_review is True
