from pathlib import Path

import pymupdf
import pytest

from app.core.config import settings
from app.crud.document import get_user_storage_bytes
from app.services.document_artifacts import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactNotReadyError,
    require_ai_ready_artifact,
)
from app.services.tool_jobs import run_next_tool_job
from tests.conftest import TestingSessionLocal


@pytest.fixture(autouse=True)
def available_local_ner(monkeypatch):
    monkeypatch.setattr(
        "app.services.privacy_detection._detect_stanza",
        lambda _text, _language, _groups: [],
    )
    monkeypatch.setattr(
        "app.services.document_redaction._ocr_page_words",
        lambda _page: _ocr_result("Public content"),
    )


def _ocr_result(text: str):
    return (
        [
            {
                "start": 0,
                "end": len(text),
                "rect": pymupdf.Rect(72, 55, 360, 85),
                "confidence": 100.0,
            }
        ],
        text,
        100.0,
    )


def _private_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "IIN: 123456789012 email test@example.com")
    payload = document.tobytes()
    document.close()
    return payload


def _upload(client) -> tuple[int, int]:
    response = client.post(
        "/api/documents/upload",
        files={"file": ("private.pdf", _private_pdf(), "application/pdf")},
    )
    assert response.status_code == 201
    return response.json()["id"], response.json()["size_bytes"]


def _run_tools() -> None:
    while run_next_tool_job(TestingSessionLocal):
        pass


def _redact(client, document_id: int, *, only_category: str | None = None) -> dict:
    queued = client.post(
        "/api/tools/redaction/preview",
        json={"document_id": document_id, "categories": ["personal"]},
    )
    assert queued.status_code == 202
    _run_tools()
    preview = client.get(f"/api/tools/jobs/{queued.json()['id']}").json()
    selected = [
        finding["id"]
        for finding in preview["findings"]
        if only_category is None or finding["category"] == only_category
    ]
    response = client.post(
        f"/api/tools/jobs/{preview['id']}/apply-redaction",
        json={"finding_ids": selected, "mode": "black"},
    )
    assert response.status_code == 202
    _run_tools()
    return client.get(f"/api/tools/jobs/{preview['id']}").json()


def test_redaction_creates_verified_ai_ready_artifact(client, other_client):
    document_id, document_size = _upload(client)
    job = _redact(client, document_id)

    assert job["status"] == "completed"
    assert job["result_artifact_id"] is not None
    assert all(finding["text"] == "" for finding in job["findings"])

    artifact_id = job["result_artifact_id"]
    response = client.get(f"/api/tools/artifacts/{artifact_id}")
    assert response.status_code == 200
    artifact = response.json()
    assert artifact["status"] == "ready_for_ai"
    assert artifact["verification_report"]["passed"] is True
    assert artifact["coverage_report"]["checked_pages"] == [1]
    assert artifact["privacy_policy"]["flattened"] is True
    assert artifact["privacy_policy"]["selectable_text"] is False
    assert artifact["privacy_policy"]["render_dpi"] == 200
    assert artifact["size_bytes"] > 0
    assert len(artifact["source_sha256"]) == 64
    assert len(artifact["artifact_sha256"]) == 64

    assert other_client.get(f"/api/tools/artifacts/{artifact_id}").status_code == 404
    assert (
        other_client.get(f"/api/tools/artifacts/{artifact_id}/download").status_code
        == 404
    )
    assert client.get(f"/api/tools/artifacts/{artifact_id}/pages/1").status_code == 200
    download = client.get(f"/api/tools/artifacts/{artifact_id}/download")
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF-")

    with TestingSessionLocal() as db:
        assert require_ai_ready_artifact(db, artifact_id, 1).id == artifact_id
        with pytest.raises(ArtifactNotFoundError):
            require_ai_ready_artifact(db, artifact_id, 2)

    with TestingSessionLocal() as db:
        assert get_user_storage_bytes(db, 1) >= document_size + artifact["size_bytes"]
    assert (
        client.get("/api/dashboard/summary").json()["storage_bytes"]
        >= document_size + artifact["size_bytes"]
    )


def test_verifier_marks_artifact_with_remaining_pii_as_needs_review(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.document_redaction._ocr_page_words",
        lambda _page: _ocr_result("IIN: 123456789012"),
    )
    document_id, _ = _upload(client)
    job = _redact(client, document_id, only_category="EMAIL")
    artifact_id = job["result_artifact_id"]
    artifact = client.get(f"/api/tools/artifacts/{artifact_id}").json()

    assert job["status"] == "completed"
    assert artifact["status"] == "needs_review"
    assert "privacy_findings_remain" in artifact["verification_report"]["risks"]
    assert artifact["verification_report"]["remaining_finding_count"] >= 1
    with TestingSessionLocal() as db, pytest.raises(ArtifactNotReadyError):
        require_ai_ready_artifact(db, artifact_id, 1)


def test_verifier_fails_closed_when_local_detector_is_unavailable(
    client,
    monkeypatch,
):
    from app.services.privacy_detection import PrivacyDetectionUnavailable

    def unavailable(_text, language, _groups):
        raise PrivacyDetectionUnavailable(f"Local model '{language}' is unavailable")

    monkeypatch.setattr("app.services.privacy_detection._detect_stanza", unavailable)
    document_id, _ = _upload(client)
    job = _redact(client, document_id)
    artifact = client.get(
        f"/api/tools/artifacts/{job['result_artifact_id']}"
    ).json()

    assert job["status"] == "completed"
    assert artifact["status"] == "needs_review"
    assert "privacy_detector_failed" in artifact["verification_report"]["risks"]
    assert artifact["coverage_report"]["verification_completed"] is False


def test_ai_gate_fails_closed_when_artifact_file_changes(client):
    document_id, _ = _upload(client)
    job = _redact(client, document_id)
    artifact_id = job["result_artifact_id"]

    with TestingSessionLocal() as db:
        artifact = require_ai_ready_artifact(db, artifact_id, 1)
        path = Path(artifact.stored_path)
    with path.open("ab") as stream:
        stream.write(b"changed")

    with TestingSessionLocal() as db, pytest.raises(ArtifactIntegrityError):
        require_ai_ready_artifact(db, artifact_id, 1)

    artifact = client.get(f"/api/tools/artifacts/{artifact_id}").json()
    assert artifact["status"] == "failed"
    assert "integrity_check_failed" in artifact["verification_report"]["risks"]
    assert client.get(f"/api/tools/artifacts/{artifact_id}/download").status_code == 409


def test_ai_gate_fails_closed_when_flattening_attestation_is_missing(client):
    document_id, _ = _upload(client)
    job = _redact(client, document_id)
    artifact_id = job["result_artifact_id"]

    with TestingSessionLocal() as db:
        from app.models.document_artifact import DocumentArtifact

        artifact = db.get(DocumentArtifact, artifact_id)
        artifact.privacy_policy = {
            **artifact.privacy_policy,
            "flattened": False,
            "selectable_text": True,
        }
        db.commit()

    with TestingSessionLocal() as db, pytest.raises(ArtifactIntegrityError):
        require_ai_ready_artifact(db, artifact_id, 1)

    artifact = client.get(f"/api/tools/artifacts/{artifact_id}").json()
    assert artifact["status"] == "needs_review"
    assert artifact["verification_report"]["passed"] is False
    assert "protected_pdf_not_flattened" in artifact["verification_report"]["risks"]
    assert "selectable_text_present" in artifact["verification_report"]["risks"]


@pytest.mark.parametrize(
    ("field", "value", "risk"),
    [
        (
            "detector_version",
            "presidio-local-outdated",
            "privacy_detector_version_outdated",
        ),
        ("policy_version", "outdated", "privacy_policy_version_outdated"),
    ],
)
def test_ai_gate_fails_closed_when_privacy_assurance_version_is_outdated(
    client,
    field,
    value,
    risk,
):
    document_id, _ = _upload(client)
    job = _redact(client, document_id)
    artifact_id = job["result_artifact_id"]

    with TestingSessionLocal() as db:
        from app.models.document_artifact import DocumentArtifact

        artifact = db.get(DocumentArtifact, artifact_id)
        setattr(artifact, field, value)
        db.commit()

    with TestingSessionLocal() as db, pytest.raises(ArtifactIntegrityError):
        require_ai_ready_artifact(db, artifact_id, 1)

    artifact = client.get(f"/api/tools/artifacts/{artifact_id}").json()
    assert artifact["status"] == "needs_review"
    assert risk in artifact["verification_report"]["risks"]


def test_artifact_delete_removes_file_and_unlinks_tool_result(client):
    document_id, _ = _upload(client)
    job = _redact(client, document_id)
    artifact_id = job["result_artifact_id"]
    with TestingSessionLocal() as db:
        artifact = require_ai_ready_artifact(db, artifact_id, 1)
        path = Path(artifact.stored_path)
    assert path.is_file()

    response = client.delete(f"/api/tools/artifacts/{artifact_id}")
    assert response.status_code == 204
    assert not path.exists()
    assert client.get(f"/api/tools/artifacts/{artifact_id}").status_code == 404

    updated_job = client.get(f"/api/tools/jobs/{job['id']}").json()
    assert updated_job["result_artifact_id"] is None
    assert client.get(f"/api/tools/jobs/{job['id']}/download").status_code == 409


def test_deleting_source_document_cascades_artifact_and_tool_files(client):
    document_id, _ = _upload(client)
    job = _redact(client, document_id)
    artifact_id = job["result_artifact_id"]
    with TestingSessionLocal() as db:
        artifact = require_ai_ready_artifact(db, artifact_id, 1)
        path = Path(artifact.stored_path)
    assert path.is_file()

    response = client.delete(f"/api/documents/{document_id}")
    assert response.status_code == 204
    assert not path.exists()
    assert client.get(f"/api/tools/artifacts/{artifact_id}").status_code == 404
    assert client.get(f"/api/tools/jobs/{job['id']}").status_code == 404


def test_protected_copy_respects_user_storage_quota(client, monkeypatch):
    document_id, document_size = _upload(client)
    monkeypatch.setattr(settings, "session_storage_quota_bytes", document_size + 1)

    job = _redact(client, document_id)

    assert job["status"] == "failed"
    assert job["result_artifact_id"] is None
    assert "Storage quota exceeded" in job["error_message"]
    assert client.get("/api/tools/artifacts").json() == []
