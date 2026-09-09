"""Small routing smoke checks; broader quality/regression evaluation is separate."""
import pytest

from app.schemas.ai_analysis import AIAnalysisCoverage, ProtectedDocumentAnalysis
from app.services.ai import jobs
from tests.ai.test_analysis_jobs import FakeDocumentProvider, _create_artifact
from tests.conftest import TestingSessionLocal


@pytest.mark.parametrize("mode", ["local", "review", "external"])
def test_protected_processing_modes(client, pdf_document_id, monkeypatch, mode):
    artifact_id, protected_path, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    local_calls = []

    def local(path, *, task, page_texts, heartbeat):
        assert path == protected_path
        local_calls.append(path)
        heartbeat(1, 1)
        return ProtectedDocumentAnalysis(
            task=task, overview="Local result",
            coverage=AIAnalysisCoverage(pages_reviewed=[1], complete=True),
        )

    def external(name=None):
        assert mode != "local", "Local processing must never contact the cloud"
        assert name == "gemini"
        return provider

    monkeypatch.setattr(jobs, "get_ai_provider", external)
    monkeypatch.setattr(jobs, "analyze_local_document", local)
    monkeypatch.setattr(jobs, "_page_texts", lambda *args, **kwargs: ["Participant [PERSON_1]"])
    response = client.post("/api/ai/jobs", json={
        "artifact_id": artifact_id, "processing_mode": mode,
        "consent_to_external_processing": mode != "local",
        "acknowledge_provider_data_terms": mode != "local",
    })
    assert response.status_code == 202, response.text
    assert jobs.run_next_ai_job(TestingSessionLocal)
    result = client.get(f"/api/ai/jobs/{response.json()['id']}").json()
    assert result["status"] == "completed", result
    assert bool(local_calls) == (mode != "external")
    assert bool(provider.uploaded_paths) == (mode != "local")
    assert ("external_review" in result["result"]) == (mode == "review")
    assert not result["remote_file_present"]


def test_external_review_requires_consent(client, pdf_document_id):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    response = client.post("/api/ai/jobs", json={
        "artifact_id": artifact_id, "processing_mode": "review",
    })
    assert response.status_code == 400


def test_cloud_failure_preserves_local_result(client, pdf_document_id, monkeypatch):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider(fail_once=True)
    monkeypatch.setattr(jobs, "get_ai_provider", lambda name=None: provider)
    monkeypatch.setattr(jobs, "_page_texts", lambda *args, **kwargs: ["Participant [PERSON_1]"])
    monkeypatch.setattr(jobs, "analyze_local_document", lambda *args, **kwargs: ProtectedDocumentAnalysis(
        task="content_review", overview="Saved local result",
        coverage=AIAnalysisCoverage(pages_reviewed=[1], complete=True),
    ))
    response = client.post("/api/ai/jobs", json={
        "artifact_id": artifact_id, "processing_mode": "review",
        "consent_to_external_processing": True, "acknowledge_provider_data_terms": True,
    })
    assert response.status_code == 202
    assert jobs.run_next_ai_job(TestingSessionLocal)
    result = client.get(f"/api/ai/jobs/{response.json()['id']}").json()
    assert result["status"] == "retry_scheduled"
    assert result["result"]["local_analysis"]["overview"] == "Saved local result"
