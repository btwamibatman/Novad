from io import BytesIO
import os
from pathlib import Path
import sys
from types import SimpleNamespace

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.core.config import settings
from app.services import text_analysis
from app.services.file_storage import resolve_stored_path


def make_pdf_with_text(text: str) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {
                    NameObject("/F1"): DictionaryObject(
                        {
                            NameObject("/Type"): NameObject("/Font"),
                            NameObject("/Subtype"): NameObject("/Type1"),
                            NameObject("/BaseFont"): NameObject("/Helvetica"),
                        }
                    )
                }
            )
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode("latin-1"))
    page[NameObject("/Contents")] = stream

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def make_pdf_without_text() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def upload_txt(client, filename: str = "sample.txt", content: bytes | None = None):
    payload = content or b"This document contains enough English text for language detection."
    return client.post(
        "/api/documents/upload",
        files={"file": (filename, payload, "text/plain")},
    )


def test_upload_txt_document(client):
    response = upload_txt(client)

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 1
    assert data["filename"] == "sample.txt"
    assert data["content_type"] == "text/plain"
    assert data["status"] == "uploaded"


def test_reject_empty_upload(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Uploaded file is empty"


def test_reject_unsupported_upload(client):
    response = client.post(
        "/api/documents/upload",
        files={"file": ("table.csv", b"a,b\n1,2", "text/csv")},
    )

    assert response.status_code == 415


def test_upload_txt_with_charset_content_type(client):
    response = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "charset.txt",
                b"This document uses a charset content type header.",
                "text/plain; charset=utf-8",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["content_type"] == "text/plain"


def test_resolve_stored_path_does_not_duplicate_storage_dir(tmp_path):
    relative_storage_dir = Path(os.path.relpath(tmp_path / "storage" / "uploads", Path.cwd()))
    settings.storage_dir = str(relative_storage_dir)
    stored_path = relative_storage_dir / "sample.pdf"
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    stored_path.write_bytes(b"pdf")

    assert resolve_stored_path(str(stored_path)) == stored_path


def test_list_and_get_document(client, txt_document_id):
    response = client.get("/api/documents")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.get(f"/api/documents/{txt_document_id}")
    assert response.status_code == 200
    assert response.json()["id"] == txt_document_id


def test_analyze_txt_document(client, txt_document_id):
    response = client.post(f"/api/documents/{txt_document_id}/analyze")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert data["detected_language"] == "en"
    assert data["word_count"] > 5
    assert "English text" in data["extracted_text"]


def test_summarize_requires_processed_document(client, txt_document_id):
    response = client.post(f"/api/documents/{txt_document_id}/summarize")

    assert response.status_code == 400
    assert response.json()["detail"] == "Document must be analyzed first"


def test_summarize_processed_document(client, txt_document_id, monkeypatch):
    client.post(f"/api/documents/{txt_document_id}/analyze")

    def fake_summarize_text(text: str) -> tuple[str, str]:
        assert "English text" in text
        return "Short AI summary for this document.", "test-gemini"

    monkeypatch.setattr(
        "app.api.routes.documents.ai_summary.summarize_text",
        fake_summarize_text,
    )

    response = client.post(f"/api/documents/{txt_document_id}/summarize")

    assert response.status_code == 200
    data = response.json()
    assert data["ai_summary"] == "Short AI summary for this document."
    assert data["ai_model"] == "test-gemini"
    assert data["ai_error"] is None


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


def test_delete_document_removes_database_record_and_file(client):
    upload = upload_txt(client)
    assert upload.status_code == 201
    document_id = upload.json()["id"]
    assert list(Path(settings.storage_dir).glob("*"))

    response = client.delete(f"/api/documents/{document_id}")
    assert response.status_code == 204

    response = client.get(f"/api/documents/{document_id}")
    assert response.status_code == 404
    assert not list(Path(settings.storage_dir).glob("*"))
