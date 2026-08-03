from io import BytesIO

import pymupdf

from app.services.tool_jobs import run_next_tool_job
from tests.conftest import TestingSessionLocal


def _pdf_with_private_text() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "IIN: 123456789012 email test@example.com")
    payload = document.tobytes()
    document.close()
    return payload


def _upload_private_pdf(client) -> int:
    response = client.post(
        "/api/documents/upload",
        files={"file": ("private.pdf", _pdf_with_private_text(), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _run_tools() -> None:
    while run_next_tool_job(TestingSessionLocal):
        pass


def test_low_compression_runs_locally_and_returns_download(client):
    document_id = _upload_private_pdf(client)
    queued = client.post(
        "/api/tools/compress",
        json={"document_id": document_id, "mode": "low"},
    )
    assert queued.status_code == 202

    _run_tools()
    job = client.get(f"/api/tools/jobs/{queued.json()['id']}").json()
    assert job["status"] == "completed"
    assert job["result_meta"]["pipeline"].startswith("pymupdf-lossless")

    download = client.get(f"/api/tools/jobs/{job['id']}/download")
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF-")


def test_redaction_requires_preview_and_physically_removes_selected_text(client):
    document_id = _upload_private_pdf(client)
    queued = client.post(
        "/api/tools/redaction/preview",
        json={"document_id": document_id, "categories": ["personal"]},
    )
    assert queued.status_code == 202
    _run_tools()

    preview = client.get(f"/api/tools/jobs/{queued.json()['id']}").json()
    assert preview["status"] == "review"
    assert {item["category"] for item in preview["findings"]} >= {"IIN", "EMAIL"}
    page = client.get(f"/api/tools/jobs/{preview['id']}/pages/1")
    assert page.status_code == 200
    assert page.headers["content-type"] == "image/png"

    selected_ids = [item["id"] for item in preview["findings"]]
    applied = client.post(
        f"/api/tools/jobs/{preview['id']}/apply-redaction",
        json={"finding_ids": selected_ids, "mode": "black"},
    )
    assert applied.status_code == 202
    _run_tools()

    download = client.get(f"/api/tools/jobs/{preview['id']}/download")
    assert download.status_code == 200
    with pymupdf.open(stream=download.content, filetype="pdf") as document:
        result_text = "".join(page.get_text() for page in document)
    assert "123456789012" not in result_text
    assert "test@example.com" not in result_text


def test_pdf_to_word_uses_editable_local_pipeline(client):
    document_id = _upload_private_pdf(client)
    queued = client.post("/api/tools/pdf-to-word", json={"document_id": document_id})
    assert queued.status_code == 202
    _run_tools()

    job = client.get(f"/api/tools/jobs/{queued.json()['id']}").json()
    assert job["status"] == "completed"
    assert job["result_meta"]["ocr_page_count"] == 0
    download = client.get(f"/api/tools/jobs/{job['id']}/download")
    assert download.status_code == 200
    assert BytesIO(download.content).read(2) == b"PK"


def test_tool_jobs_are_scoped_to_the_current_user(client, other_client):
    document_id = _upload_private_pdf(client)
    queued = client.post(
        "/api/tools/compress",
        json={"document_id": document_id, "mode": "low"},
    )
    job_id = queued.json()["id"]
    assert other_client.get(f"/api/tools/jobs/{job_id}").status_code == 404
    assert other_client.get(f"/api/tools/jobs/{job_id}/download").status_code == 404
