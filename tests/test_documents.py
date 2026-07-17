import os
from pathlib import Path
import sys
from types import SimpleNamespace

from pypdf import PdfReader

from app.core.config import settings
from app.services import ai_content_review, ai_layout_review, text_analysis
from app.services.file_storage import resolve_stored_path
from tests.pdf_helpers import (
    make_pdf_with_text,
    make_pdf_with_text_and_blank_pages,
    make_pdf_without_text,
)


def upload_pdf(client, filename: str = "sample.pdf", text: str | None = None):
    payload = make_pdf_with_text(
        text or "This document contains enough English text for language detection."
    )
    return client.post(
        "/api/documents/upload",
        files={"file": (filename, payload, "application/pdf")},
    )


def test_upload_pdf_document(client):
    response = upload_pdf(client)

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 1
    assert data["filename"] == "sample.pdf"
    assert data["content_type"] == "application/pdf"
    assert data["status"] == "uploaded"


def test_reject_empty_upload(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is empty"


def test_reject_non_pdf_upload(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("notes.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Only PDF files are supported"


def test_reject_pdf_extension_with_non_pdf_content(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("fake.pdf", b"plain text", "application/pdf")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Uploaded file content is not a PDF"


def test_upload_pdf_with_charset_content_type(client):
    response = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "charset.pdf",
                make_pdf_with_text("This PDF uses a charset content type header."),
                "application/pdf; charset=binary",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["content_type"] == "application/pdf"


def test_resolve_stored_path_does_not_duplicate_storage_dir(tmp_path):
    relative_storage_dir = Path(os.path.relpath(tmp_path / "storage" / "uploads", Path.cwd()))
    settings.storage_dir = str(relative_storage_dir)
    stored_path = relative_storage_dir / "sample.pdf"
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    stored_path.write_bytes(b"pdf")

    assert resolve_stored_path(str(stored_path)) == stored_path


def test_list_and_get_document(client, pdf_document_id):
    response = client.get("/api/documents")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.get(f"/api/documents/{pdf_document_id}")
    assert response.status_code == 200
    assert response.json()["id"] == pdf_document_id


def test_documents_are_scoped_to_user(client, other_client, pdf_document_id):
    response = other_client.get("/api/documents")
    assert response.status_code == 200
    assert response.json() == []

    response = other_client.get(f"/api/documents/{pdf_document_id}")
    assert response.status_code == 404


def test_session_endpoint_returns_authenticated_session(client):
    response = client.get("/api/session")

    assert response.status_code == 200
    assert response.json()["session_id"]
    assert response.json()["user_id"]
    assert response.json()["expires_at"]
    assert "document_session" in response.cookies


def test_upload_rejects_session_storage_quota(client, monkeypatch):
    monkeypatch.setattr(settings, "session_storage_quota_bytes", 10)

    response = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "large.pdf",
                make_pdf_with_text("This payload is too large for the configured quota."),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 413
    assert response.json()["detail"]["message"] == "Session storage quota exceeded"


def test_analyze_pdf_document(client, pdf_document_id):
    response = client.post(f"/api/documents/{pdf_document_id}/analyze")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert data["detected_language"] == "en"
    assert data["language_distribution"] == {"en": 1.0}
    assert data["word_count"] > 5
    assert "English text" in data["extracted_text"]
    assert data["extraction_quality"] == "high"
    assert data["extraction_quality_meta"]["requires_manual_review"] is False
def test_summarize_requires_processed_document(client, pdf_document_id):
    response = client.post(f"/api/documents/{pdf_document_id}/summarize")

    assert response.status_code == 400
    assert response.json()["detail"] == "Document must be analyzed first"


def test_summarize_processed_document(client, pdf_document_id, monkeypatch):
    client.post(f"/api/documents/{pdf_document_id}/analyze")

    def fake_summarize_text(text: str, extraction_quality: str) -> tuple[str, str]:
        assert "English text" in text
        assert extraction_quality == "high"
        return "Short AI summary for this document.", "test-gemini"

    monkeypatch.setattr(
        "app.api.routes.documents.ai_summary.summarize_text",
        fake_summarize_text,
    )

    response = client.post(f"/api/documents/{pdf_document_id}/summarize")

    assert response.status_code == 200
    data = response.json()
    assert data["ai_summary"] == "Short AI summary for this document."
    assert data["ai_model"] == "test-gemini"
    assert data["ai_error"] is None


def test_ask_requires_processed_document(client, pdf_document_id):
    response = client.post(
        f"/api/documents/{pdf_document_id}/ask",
        json={"question": "What is this file about?", "history": []},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Document must be analyzed first"


def test_ask_processed_document(client, pdf_document_id, monkeypatch):
    client.post(f"/api/documents/{pdf_document_id}/analyze")

    def fake_answer_document_question(
        text: str,
        question: str,
        history: list[dict[str, str]],
        extraction_quality: str,
    ):
        assert "English text" in text
        assert question == "What language is this?"
        assert history == [{"role": "user", "content": "Previous question"}]
        assert extraction_quality == "high"
        return "The document is in English.", "test-gemini", False

    monkeypatch.setattr(
        "app.api.routes.documents.ai_summary.answer_document_question",
        fake_answer_document_question,
    )

    response = client.post(
        f"/api/documents/{pdf_document_id}/ask",
        json={
            "question": "What language is this?",
            "history": [{"role": "user", "content": "Previous question"}],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "The document is in English.",
        "model": "test-gemini",
        "truncated_context": False,
    }


def test_ask_processed_document_uses_relevant_chunk(client, monkeypatch):
    early_text = "early section " * 220
    late_text = "specialinvoiceend final amount is forty two. " * 40
    upload = upload_pdf(
        client,
        filename="long.pdf",
        text=f"{early_text} {late_text}",
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]
    client.post(f"/api/documents/{document_id}/analyze")

    def fake_answer_document_question(
        text: str,
        question: str,
        history: list[dict[str, str]],
        extraction_quality: str,
    ):
        assert "specialinvoiceend" in text
        assert question == "What is the specialinvoiceend amount?"
        assert history == []
        assert extraction_quality == "high"
        return "The amount is forty two.", "test-gemini", False

    monkeypatch.setattr(
        "app.api.routes.documents.ai_summary.answer_document_question",
        fake_answer_document_question,
    )

    response = client.post(
        f"/api/documents/{document_id}/ask",
        json={"question": "What is the specialinvoiceend amount?", "history": []},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "The amount is forty two."


def test_ask_rejects_blank_question(client, pdf_document_id):
    client.post(f"/api/documents/{pdf_document_id}/analyze")

    response = client.post(
        f"/api/documents/{pdf_document_id}/ask",
        json={"question": "   ", "history": []},
    )

    assert response.status_code == 422


def test_ask_rate_limit_returns_retry_after(client, pdf_document_id, monkeypatch):
    client.post(f"/api/documents/{pdf_document_id}/analyze")

    def fake_answer_document_question(
        text: str,
        question: str,
        history: list[dict[str, str]],
        extraction_quality: str,
    ):
        assert extraction_quality == "high"
        return "Answer.", "test-gemini", False

    monkeypatch.setattr(
        "app.api.routes.documents.ai_summary.answer_document_question",
        fake_answer_document_question,
    )

    for _ in range(10):
        response = client.post(
            f"/api/documents/{pdf_document_id}/ask",
            json={"question": "What is this?", "history": []},
        )
        assert response.status_code == 200

    response = client.post(
        f"/api/documents/{pdf_document_id}/ask",
        json={"question": "What is this?", "history": []},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"]


def test_analyze_pdf_with_text_layer(client):
    pdf_bytes = make_pdf_with_text("This PDF contains extractable English text for analysis.")
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("sample.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload.status_code == 201

    response = client.post(f"/api/documents/{upload.json()['id']}/analyze")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert data["detected_language"] == "en"
    assert "extractable English text" in data["extracted_text"]


def test_analyze_pdf_uses_ocr_fallback_when_text_layer_is_empty(client, monkeypatch):
    pdf_bytes = make_pdf_without_text()
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("scan.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload.status_code == 201

    def fake_run_ocr(input_path: Path, output_path: Path) -> int:
        assert input_path.exists()
        output_path.write_bytes(make_pdf_with_text("OCR fallback extracted English text for analysis."))
        return 0

    monkeypatch.setattr("app.services.text_analysis.run_ocr", fake_run_ocr)

    response = client.post(f"/api/documents/{upload.json()['id']}/analyze")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert "OCR fallback extracted English text" in data["extracted_text"]
    assert data["extraction_quality"] == "medium"
    assert data["extraction_quality_meta"]["requires_manual_review"] is True
    assert data["extraction_quality_meta"]["manual_review_pages"] == [1]


def test_analyze_pdf_batches_weak_pages_for_mixed_pdf(client, monkeypatch):
    pdf_bytes = make_pdf_with_text_and_blank_pages("First page has extractable English text.")
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("mixed.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload.status_code == 201
    ocr_inputs = []

    def fake_run_ocr(input_path: Path, output_path: Path) -> int:
        ocr_inputs.append(input_path)
        assert len(PdfReader(str(input_path)).pages) == 1
        output_path.write_bytes(make_pdf_with_text("Second page OCR English text."))
        return 0

    monkeypatch.setattr("app.services.text_analysis.run_ocr", fake_run_ocr)

    response = client.post(f"/api/documents/{upload.json()['id']}/analyze")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert "First page has extractable English text" in data["extracted_text"]
    assert "Second page OCR English text" in data["extracted_text"]
    assert len(ocr_inputs) == 1


def test_analyze_pdf_sends_multiple_weak_pages_to_one_ocr_batch(client, monkeypatch):
    pdf_bytes = make_pdf_with_text_and_blank_pages(
        "First page has extractable English text.",
        blank_page_count=2,
    )
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("mixed.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload.status_code == 201
    ocr_call_count = 0

    def fake_run_ocr(input_path: Path, output_path: Path) -> int:
        nonlocal ocr_call_count
        ocr_call_count += 1
        assert len(PdfReader(str(input_path)).pages) == 2
        output_path.write_bytes(
            make_pdf_with_text_and_blank_pages(
                "Second page OCR English text.",
                blank_page_count=1,
            )
        )
        return 0

    monkeypatch.setattr("app.services.text_analysis.run_ocr", fake_run_ocr)

    response = client.post(f"/api/documents/{upload.json()['id']}/analyze")

    assert response.status_code == 200
    assert response.json()["status"] == "processed"
    assert ocr_call_count == 1


def test_run_ocr_uses_configured_russian_kazakh_english_languages(tmp_path, monkeypatch):
    input_path = tmp_path / "input.pdf"
    output_path = tmp_path / "output.pdf"
    input_path.write_bytes(make_pdf_without_text())
    captured_kwargs = {}

    def fake_ocr(input_file, output_file, **kwargs):
        captured_kwargs.update(kwargs)
        Path(output_file).write_bytes(make_pdf_with_text("OCR fallback extracted English text for analysis."))
        return 0

    monkeypatch.setattr(text_analysis.settings, "ocr_languages", "rus+kaz+eng")
    monkeypatch.setitem(sys.modules, "ocrmypdf", SimpleNamespace(ocr=fake_ocr))

    assert text_analysis.run_ocr(input_path, output_path) == 0
    assert captured_kwargs["language"] == ("rus", "kaz", "eng")
    assert captured_kwargs["force_ocr"] is True
    assert "skip_text" not in captured_kwargs


def test_analyze_pdf_reports_ocr_exit_failure(client, monkeypatch):
    pdf_bytes = make_pdf_without_text()
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("scan.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload.status_code == 201

    def fake_run_ocr(input_path: Path, output_path: Path) -> int:
        return 2

    monkeypatch.setattr("app.services.text_analysis.run_ocr", fake_run_ocr)

    response = client.post(f"/api/documents/{upload.json()['id']}/analyze")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["extraction_quality"] == "unknown"
    assert data["error_message"] == "OCR failed: OCR engine exited with code 2"


def test_analyze_pdf_reports_no_text_after_ocr(client, monkeypatch):
    pdf_bytes = make_pdf_without_text()
    upload = client.post(
        "/api/documents/upload",
        files={"file": ("scan.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload.status_code == 201

    def fake_run_ocr(input_path: Path, output_path: Path) -> int:
        output_path.write_bytes(make_pdf_without_text())
        return 0

    monkeypatch.setattr("app.services.text_analysis.run_ocr", fake_run_ocr)

    response = client.post(f"/api/documents/{upload.json()['id']}/analyze")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert "no readable text was found after OCR" in data["error_message"]


def test_ocr_language_missing_error_is_user_readable(monkeypatch):
    monkeypatch.setattr(text_analysis.settings, "ocr_languages", "rus+kaz+eng")

    message = text_analysis.format_ocr_error(RuntimeError("Error opening data file kaz.traineddata"))

    assert message == "OCR failed: configured language data is missing (rus+kaz+eng)"


def test_content_review_requires_processed_document(client, pdf_document_id):
    response = client.post(
        f"/api/documents/{pdf_document_id}/content-review",
        json={"mode": "quick"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Document must be analyzed first"


def test_content_review_persists_result(client, pdf_document_id, monkeypatch):
    client.post(f"/api/documents/{pdf_document_id}/analyze")

    def fake_review(chunks, mode):
        assert chunks
        assert chunks[0].extraction_method == "pypdf"
        assert mode == "thorough"
        return ai_content_review.ContentReviewResult(
            text="The document needs two language corrections.",
            model="test-model",
            mode="thorough",
            total_chars=120,
            reviewed_chars=120,
            batch_count=2,
            complete=True,
        )

    monkeypatch.setattr(ai_content_review, "review_document_content", fake_review)

    response = client.post(
        f"/api/documents/{pdf_document_id}/content-review",
        json={"mode": "thorough"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["content_review"] == "The document needs two language corrections."
    assert data["content_review_model"] == "test-model"
    assert data["content_review_mode"] == "thorough"
    assert data["content_review_error"] is None
    assert data["content_review_meta"]["complete"] is True
    assert data["content_review_meta"]["batch_count"] == 2
    assert data["content_review_meta"]["extraction_quality"] == "high"
    assert data["content_review_meta"]["requires_manual_review"] is False


def test_content_review_reports_synchronous_size_limit(client, pdf_document_id, monkeypatch):
    client.post(f"/api/documents/{pdf_document_id}/analyze")

    def fake_review(chunks, mode):
        raise ai_content_review.ContentReviewTooLarge("Use quick review")

    monkeypatch.setattr(ai_content_review, "review_document_content", fake_review)

    response = client.post(
        f"/api/documents/{pdf_document_id}/content-review",
        json={"mode": "thorough"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Use quick review"
    stored = client.get(f"/api/documents/{pdf_document_id}").json()
    assert stored["content_review_error"] == "Use quick review"


def test_layout_review_does_not_require_text_analysis(client, pdf_document_id, monkeypatch):
    def fake_review(path: Path):
        assert path.exists()
        return ai_layout_review.LayoutReviewResult(
            text="The visual layout is generally consistent.",
            model="test-vision-model",
            total_pages=6,
            reviewed_pages=[1, 4, 6],
            dpi=150,
            complete=False,
        )

    monkeypatch.setattr(ai_layout_review, "review_pdf_layout", fake_review)

    response = client.post(f"/api/documents/{pdf_document_id}/layout-review")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "uploaded"
    assert data["layout_review"] == "The visual layout is generally consistent."
    assert data["layout_review_model"] == "test-vision-model"
    assert data["layout_review_meta"]["reviewed_pages"] == [1, 4, 6]
    assert data["layout_review_meta"]["complete"] is False
    assert data["layout_review_meta"]["adaptive_dpi"] is False
    assert data["layout_review_meta"]["requested_dpi"] == 150
    assert data["layout_review_meta"]["external_processing"] is True


def test_layout_review_rejects_corrupted_pdf_as_input_error(client):
    upload = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "broken.pdf",
                b"%PDF-1.7\nnot a valid PDF structure",
                "application/pdf",
            )
        },
    )
    assert upload.status_code == 201

    response = client.post(f"/api/documents/{upload.json()['id']}/layout-review")

    assert response.status_code == 400
    assert "invalid or corrupted" in response.json()["detail"]


def test_delete_document_removes_database_record_and_file(client):
    upload = upload_pdf(client)
    assert upload.status_code == 201
    document_id = upload.json()["id"]
    assert list(Path(settings.storage_dir).glob("*"))

    response = client.delete(f"/api/documents/{document_id}")
    assert response.status_code == 204

    response = client.get(f"/api/documents/{document_id}")
    assert response.status_code == 404
    assert not list(Path(settings.storage_dir).glob("*"))
