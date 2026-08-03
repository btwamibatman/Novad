from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.file_storage import remove_stored_file
from app.services.pii_masking import PIIMaskingSession, RegexPIIRecognizer
from tests.pdf_helpers import make_pdf_with_text


def test_upload_strips_path_segments_and_accepts_unicode_filename(client):
    response = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "..\\..\\договор📄.pdf",
                make_pdf_with_text("Traversal-safe filename test."),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 201
    assert response.json()["filename"] == "договор📄.pdf"
    stored_files = list(Path(settings.storage_dir).iterdir())
    assert len(stored_files) == 1
    assert stored_files[0].suffix == ".pdf"
    assert stored_files[0].is_file()


def test_upload_rejects_payload_over_limit_plus_one_byte(client, monkeypatch):
    payload = make_pdf_with_text("Boundary size test.")
    monkeypatch.setattr(settings, "max_upload_size_bytes", len(payload) - 1)

    response = client.post(
        "/api/documents/upload",
        files={"file": ("boundary.pdf", payload, "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "File is too large"
    assert list(Path(settings.storage_dir).iterdir()) == []


def test_download_and_delete_are_scoped_to_the_owner(client, other_client, pdf_document_id):
    assert other_client.get(f"/api/documents/{pdf_document_id}/download").status_code == 404
    assert other_client.delete(f"/api/documents/{pdf_document_id}").status_code == 404


def test_concurrent_remove_stored_file_is_idempotent_under_race(tmp_path):
    path = Path(settings.storage_dir) / "race.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"pdf")

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(remove_stored_file, str(path))
        second = executor.submit(remove_stored_file, str(path))
        first.result()
        second.result()

    assert not path.exists()


def test_regex_pii_masking_handles_ocr_spacing_and_mixed_language_noise():
    session = PIIMaskingSession([RegexPIIRecognizer()], enabled=True)

    masked = session.mask(
        "Құжаттағы ИИН 990101123456 және email user@example.kz мәтіннің ішінде тұр."
    )

    assert "990101123456" not in masked
    assert "user@example.kz" not in masked
    assert session.restore(masked).startswith("Құжаттағы ИИН 990101123456")