from datetime import timedelta
import json
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.models._utils import utc_now
from app.models.ai_analysis_job import AIAnalysisJob
from app.models.document import Document
from app.models.document_artifact import DocumentArtifact
from app.services.ai.jobs import (
    _commit_deduplicated_job,
    _stop_cancelled_job,
    run_next_ai_job,
)
from app.services.ai.provider import (
    AIGenerationResult,
    AIProviderError,
    AIRemoteDocument,
)
from app.services.documents.artifacts import POLICY_VERSION, sha256_file
from app.services.privacy_detection import PRIVACY_ENGINE_VERSION
from tests.conftest import TestingSessionLocal
from tests.pdf_helpers import make_pdf_with_text


class FakeDocumentProvider:
    def __init__(self, *, fail_once: bool = False) -> None:
        self.fail_once = fail_once
        self.fail_delete = False
        self.uploaded_paths: list[Path] = []
        self.generated = 0
        self.get_calls: list[str] = []
        self.deleted: list[str] = []
        self.remote = AIRemoteDocument(
            name="files/protected-1",
            uri="https://provider.test/files/protected-1",
            mime_type="application/pdf",
            state="ACTIVE",
            expires_at=utc_now() + timedelta(hours=48),
        )

    def upload_document(self, document):
        self.uploaded_paths.append(document.path)
        return self.remote

    def get_document(self, name: str):
        self.get_calls.append(name)
        return self.remote

    def delete_document(self, name: str) -> None:
        if self.fail_delete:
            raise AIProviderError("delete failed", code=503, retryable=True)
        self.deleted.append(name)

    def generate_document(self, prompt, document, **kwargs):
        self.generated += 1
        if self.fail_once:
            self.fail_once = False
            raise AIProviderError(
                "quota",
                code=429,
                retryable=True,
                retry_after_seconds=7,
                provider_detail="quota exhausted",
            )
        task = next(
            candidate
            for candidate in ("summary", "content_review", "layout_review")
            if f"Задача: {candidate}." in prompt
        )
        payload = {
            "task": task,
            "overview": "Защищённый документ проверен.",
            "verdict": "Критических проблем нет.",
            "key_points": [
                {
                    "text": "Указан защищённый участник",
                    "page": 1,
                    "evidence": "Participant [PERSON_1]",
                }
            ],
            "findings": [],
            "coverage": {
                "pages_reviewed": [1],
                "complete": True,
                "limitations": [],
            },
        }
        return AIGenerationResult(
            text=json.dumps(payload, ensure_ascii=False),
            model="test-model",
            usage={"total_token_count": 42},
        )


def _create_artifact(pdf_document_id: int, *, status: str = "ready_for_ai"):
    protected_path = (
        Path(settings.storage_dir).parent
        / "tools"
        / "results"
        / "protected-for-ai.pdf"
    )
    protected_path.parent.mkdir(parents=True, exist_ok=True)
    protected_path.write_bytes(
        make_pdf_with_text("Participant [PERSON_1] completed the protected project.")
    )
    with TestingSessionLocal() as db:
        document = db.get(Document, pdf_document_id)
        assert document is not None
        artifact = DocumentArtifact(
            user_id=document.user_id,
            source_document_id=document.id,
            status=status,
            filename="protected-for-ai.pdf",
            content_type="application/pdf",
            stored_path=str(protected_path.resolve()),
            size_bytes=protected_path.stat().st_size,
            source_sha256=sha256_file(Path(document.stored_path)),
            artifact_sha256=sha256_file(protected_path),
            privacy_policy={
                "categories": ["personal", "financial", "visual"],
                "flattened": True,
                "selectable_text": False,
            },
            policy_version=POLICY_VERSION,
            detector_version=PRIVACY_ENGINE_VERSION,
            coverage_report={
                "page_count": 1,
                "checked_pages": [1],
                "unchecked_pages": [],
                "verification_completed": True,
            },
            verification_report={"passed": status == "ready_for_ai", "risks": []},
            verified_at=utc_now(),
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return artifact.id, protected_path, Path(document.stored_path)


def _enqueue(client, artifact_id: int, **overrides):
    payload = {
        "artifact_id": artifact_id,
        "task": "content_review",
        "retention": "delete_after_analysis",
        "consent_to_external_processing": True,
        "acknowledge_provider_data_terms": True,
        **overrides,
    }
    return client.post("/api/ai/jobs", json=payload)


def test_provider_info_exposes_policy_without_credentials(client):
    response = client.get("/api/ai/provider-info")

    assert response.status_code == 200
    assert response.json() == {
        "provider": settings.ai_provider,
        "model": settings.gemini_model,
        "service_tier": settings.gemini_service_tier,
        "max_remote_retention_hours": 48,
        "requires_verified_artifact": True,
    }
    assert "key" not in json.dumps(response.json()).casefold()


def test_ai_job_requires_consent_and_verified_artifact(client, pdf_document_id):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    missing_consent = client.post(
        "/api/ai/jobs",
        json={"artifact_id": artifact_id, "task": "content_review"},
    )
    assert missing_consent.status_code == 400

    unready_id, _, _ = _create_artifact(pdf_document_id, status="needs_review")
    assert _enqueue(client, unready_id).status_code == 409


def test_identical_enqueue_is_idempotent_across_request_sessions(
    client, pdf_document_id
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)

    first = _enqueue(client, artifact_id)
    second = _enqueue(client, artifact_id)

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]
    with TestingSessionLocal() as db:
        jobs = list(db.scalars(select(AIAnalysisJob)))
        assert len(jobs) == 1
        assert jobs[0].dedupe_key
        assert jobs[0].consent_snapshot["artifact_policy_version"] == POLICY_VERSION
        assert jobs[0].consent_snapshot["detector_version"] == PRIVACY_ENGINE_VERSION
        assert jobs[0].consent_snapshot["provider_terms_url"] == (
            "https://ai.google.dev/gemini-api/terms"
        )


def test_unique_dedupe_collision_recovers_the_committed_job(
    client, pdf_document_id
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    first_id = _enqueue(client, artifact_id).json()["id"]

    with TestingSessionLocal() as db:
        first = db.get(AIAnalysisJob, first_id)
        duplicate = AIAnalysisJob(
            user_id=first.user_id,
            artifact_id=first.artifact_id,
            task=first.task,
            provider=first.provider,
            model=first.model,
            artifact_sha256=first.artifact_sha256,
            dedupe_key=first.dedupe_key,
            retention=first.retention,
            prompt_version=first.prompt_version,
            schema_version=first.schema_version,
            consent_snapshot=dict(first.consent_snapshot),
        )
        db.add(duplicate)

        recovered = _commit_deduplicated_job(db, duplicate, first.dedupe_key)

        assert recovered.id == first_id
        assert len(list(db.scalars(select(AIAnalysisJob)))) == 1


def test_cancelled_job_releases_its_dedupe_key(client, pdf_document_id):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    first_id = _enqueue(client, artifact_id).json()["id"]

    assert client.post(f"/api/ai/jobs/{first_id}/cancel").status_code == 200
    second_id = _enqueue(client, artifact_id).json()["id"]

    assert second_id != first_id
    with TestingSessionLocal() as db:
        assert db.get(AIAnalysisJob, first_id).dedupe_key is None
        assert db.get(AIAnalysisJob, second_id).dedupe_key is not None


def test_dedupe_does_not_cross_provider_service_tiers(
    client, pdf_document_id, monkeypatch
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    monkeypatch.setattr(settings, "gemini_service_tier", "unpaid")
    unpaid_id = _enqueue(client, artifact_id).json()["id"]

    monkeypatch.setattr(settings, "gemini_service_tier", "paid")
    paid_id = _enqueue(client, artifact_id).json()["id"]

    assert paid_id != unpaid_id
    with TestingSessionLocal() as db:
        assert db.get(AIAnalysisJob, unpaid_id).consent_snapshot["service_tier"] == (
            "unpaid"
        )
        assert db.get(AIAnalysisJob, paid_id).consent_snapshot["service_tier"] == "paid"


def test_ai_job_uses_only_protected_artifact_and_deletes_one_shot_copy(
    client, other_client, pdf_document_id, monkeypatch
):
    artifact_id, protected_path, source_path = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )

    response = _enqueue(client, artifact_id)
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert other_client.get(f"/api/ai/jobs/{job_id}").status_code == 404

    assert run_next_ai_job(TestingSessionLocal) is True
    result = client.get(f"/api/ai/jobs/{job_id}").json()

    assert result["status"] == "completed"
    assert result["result"]["coverage"]["complete"] is True
    assert result["usage"] == {"total_token_count": 42}
    assert provider.uploaded_paths == [protected_path]
    assert protected_path != source_path
    assert provider.deleted == ["files/protected-1"]
    assert result["provider_file_expires_at"] is None


def test_retryable_provider_error_is_persistently_rescheduled(
    client, pdf_document_id, monkeypatch
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider(fail_once=True)
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )

    job_id = _enqueue(client, artifact_id).json()["id"]
    assert run_next_ai_job(TestingSessionLocal) is True
    scheduled = client.get(f"/api/ai/jobs/{job_id}").json()
    assert scheduled["status"] == "retry_scheduled"
    assert scheduled["error_code"] == "429"
    assert scheduled["attempts"] == 1

    with TestingSessionLocal() as db:
        job = db.get(AIAnalysisJob, job_id)
        job.not_before = utc_now() - timedelta(seconds=1)
        db.commit()
    assert run_next_ai_job(TestingSessionLocal) is True
    quota_wait = client.get(f"/api/ai/jobs/{job_id}").json()
    assert quota_wait["status"] == "retry_scheduled"
    assert quota_wait["stage"] == "quota_wait"
    assert quota_wait["attempts"] == 1
    with TestingSessionLocal() as db:
        job = db.get(AIAnalysisJob, job_id)
        job.not_before = utc_now() - timedelta(seconds=1)
        job.provider_requested_at = utc_now() - timedelta(seconds=13)
        db.commit()
    assert run_next_ai_job(TestingSessionLocal) is True
    completed = client.get(f"/api/ai/jobs/{job_id}").json()
    assert completed["status"] == "completed"
    assert completed["attempts"] == 2
    assert len(provider.uploaded_paths) == 1


def test_failed_job_releases_its_dedupe_key(
    client, pdf_document_id, monkeypatch
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()

    def failed_generation(*args, **kwargs):
        raise AIProviderError("fatal provider error", code=500, retryable=False)

    monkeypatch.setattr(provider, "generate_document", failed_generation)
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )
    first_id = _enqueue(client, artifact_id).json()["id"]

    assert run_next_ai_job(TestingSessionLocal) is True
    assert client.get(f"/api/ai/jobs/{first_id}").json()["status"] == "failed"
    second_id = _enqueue(client, artifact_id).json()["id"]

    assert second_id != first_id
    with TestingSessionLocal() as db:
        assert db.get(AIAnalysisJob, first_id).dedupe_key is None
        assert db.get(AIAnalysisJob, second_id).dedupe_key is not None


def test_retained_remote_pdf_is_reused_and_revoked_for_all_linked_jobs(
    client, pdf_document_id, monkeypatch
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )

    first_id = _enqueue(
        client, artifact_id, retention="retain_48h", task="content_review"
    ).json()["id"]
    assert run_next_ai_job(TestingSessionLocal) is True
    with TestingSessionLocal() as db:
        first = db.get(AIAnalysisJob, first_id)
        first.provider_requested_at = utc_now() - timedelta(seconds=13)
        db.commit()
    second_id = _enqueue(
        client, artifact_id, retention="retain_48h", task="summary"
    ).json()["id"]
    assert run_next_ai_job(TestingSessionLocal) is True

    assert len(provider.uploaded_paths) == 1
    assert provider.get_calls == ["files/protected-1"]
    assert provider.deleted == []

    response = client.delete(f"/api/ai/jobs/{first_id}/remote-file")
    assert response.status_code == 200
    assert provider.deleted == ["files/protected-1"]
    assert response.json()["provider_file_expires_at"] is None
    assert (
        client.get(f"/api/ai/jobs/{second_id}").json()["provider_file_expires_at"]
        is None
    )


def test_expired_provider_file_is_reconciled_for_get_and_list(
    client, pdf_document_id, monkeypatch
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )
    first_id = _enqueue(
        client, artifact_id, retention="retain_48h", task="content_review"
    ).json()["id"]
    assert run_next_ai_job(TestingSessionLocal) is True
    with TestingSessionLocal() as db:
        first = db.get(AIAnalysisJob, first_id)
        first.provider_requested_at = utc_now() - timedelta(seconds=13)
        db.commit()
    second_id = _enqueue(
        client, artifact_id, retention="retain_48h", task="summary"
    ).json()["id"]
    assert run_next_ai_job(TestingSessionLocal) is True
    with TestingSessionLocal() as db:
        first = db.get(AIAnalysisJob, first_id)
        first.provider_file_expires_at = utc_now() - timedelta(seconds=1)
        db.commit()

    first_read = client.get(f"/api/ai/jobs/{first_id}")
    listed = client.get("/api/ai/jobs")

    assert first_read.status_code == 200
    assert first_read.json()["remote_file_present"] is False
    assert first_read.json()["provider_file_expires_at"] is None
    assert first_read.json()["remote_cleanup_status"] == "deleted"
    listed_jobs = {job["id"]: job for job in listed.json()}
    assert listed_jobs[second_id]["remote_file_present"] is False
    assert listed_jobs[second_id]["remote_cleanup_status"] == "deleted"
    assert provider.deleted == []


def test_enqueue_does_not_reuse_an_expired_provider_file(
    client, pdf_document_id, monkeypatch
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )
    first_id = _enqueue(
        client, artifact_id, retention="retain_48h", task="content_review"
    ).json()["id"]
    assert run_next_ai_job(TestingSessionLocal) is True
    with TestingSessionLocal() as db:
        first = db.get(AIAnalysisJob, first_id)
        first.provider_file_expires_at = utc_now() - timedelta(seconds=1)
        first.provider_requested_at = utc_now() - timedelta(seconds=13)
        db.commit()

    second_id = _enqueue(
        client, artifact_id, retention="retain_48h", task="summary"
    ).json()["id"]
    assert client.get(f"/api/ai/jobs/{first_id}").json()["remote_file_present"] is False
    assert run_next_ai_job(TestingSessionLocal) is True

    assert client.get(f"/api/ai/jobs/{second_id}").json()["status"] == "completed"
    assert len(provider.uploaded_paths) == 2
    assert provider.get_calls == []


def test_shared_remote_file_cannot_be_deleted_while_a_linked_job_is_active(
    client, pdf_document_id, monkeypatch
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )

    first_id = _enqueue(
        client, artifact_id, retention="retain_48h", task="content_review"
    ).json()["id"]
    assert run_next_ai_job(TestingSessionLocal) is True
    second_id = _enqueue(
        client, artifact_id, retention="retain_48h", task="summary"
    ).json()["id"]
    with TestingSessionLocal() as db:
        second = db.get(AIAnalysisJob, second_id)
        second.status = "running"
        second.worker_active = True
        second.provider_file_name = provider.remote.name
        second.provider_file_uri = provider.remote.uri
        second.provider_file_expires_at = provider.remote.expires_at
        second.remote_cleanup_status = "retained"
        db.commit()

    blocked = client.delete(f"/api/ai/jobs/{first_id}/remote-file")

    assert blocked.status_code == 409
    assert provider.deleted == []
    assert client.get(f"/api/ai/jobs/{second_id}").json()["remote_file_present"] is True

    with TestingSessionLocal() as db:
        second = db.get(AIAnalysisJob, second_id)
        second.status = "completed"
        second.worker_active = False
        db.commit()

    deleted = client.delete(f"/api/ai/jobs/{first_id}/remote-file")

    assert deleted.status_code == 200
    assert provider.deleted == [provider.remote.name]
    assert client.get(f"/api/ai/jobs/{second_id}").json()["remote_file_present"] is False


def test_failed_linked_job_cleanup_clears_shared_remote_references(
    client, pdf_document_id, monkeypatch
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )

    first_id = _enqueue(
        client, artifact_id, retention="retain_48h", task="content_review"
    ).json()["id"]
    assert run_next_ai_job(TestingSessionLocal) is True
    with TestingSessionLocal() as db:
        first = db.get(AIAnalysisJob, first_id)
        first.provider_requested_at = utc_now() - timedelta(seconds=13)
        db.commit()

    def failed_generation(*args, **kwargs):
        raise AIProviderError("fatal provider error", code=500, retryable=False)

    monkeypatch.setattr(provider, "generate_document", failed_generation)
    second_id = _enqueue(
        client, artifact_id, retention="retain_48h", task="summary"
    ).json()["id"]

    assert run_next_ai_job(TestingSessionLocal) is True

    assert client.get(f"/api/ai/jobs/{second_id}").json()["status"] == "failed"
    assert client.get(f"/api/ai/jobs/{first_id}").json()["remote_file_present"] is False
    assert client.get(f"/api/ai/jobs/{second_id}").json()["remote_file_present"] is False
    assert provider.deleted == [provider.remote.name]


def test_enqueue_detects_artifact_integrity_change(client, pdf_document_id):
    artifact_id, protected_path, _ = _create_artifact(pdf_document_id)
    with protected_path.open("ab") as stream:
        stream.write(b"changed")

    assert _enqueue(client, artifact_id).status_code == 409
    with TestingSessionLocal() as db:
        artifact = db.scalar(
            select(DocumentArtifact).where(DocumentArtifact.id == artifact_id)
        )
        assert artifact.status == "failed"


def test_deleting_artifact_revokes_retained_provider_file(
    client, pdf_document_id, monkeypatch
):
    artifact_id, protected_path, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )
    job_id = _enqueue(client, artifact_id, retention="retain_48h").json()["id"]
    assert run_next_ai_job(TestingSessionLocal) is True

    response = client.delete(f"/api/tools/artifacts/{artifact_id}")

    assert response.status_code == 204
    assert provider.deleted == ["files/protected-1"]
    assert not protected_path.exists()
    assert client.get(f"/api/ai/jobs/{job_id}").status_code == 404


def test_deleting_source_document_revokes_retained_provider_file(
    client, pdf_document_id, monkeypatch
):
    artifact_id, protected_path, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )
    job_id = _enqueue(client, artifact_id, retention="retain_48h").json()["id"]
    assert run_next_ai_job(TestingSessionLocal) is True

    response = client.delete(f"/api/documents/{pdf_document_id}")

    assert response.status_code == 204
    assert provider.deleted == ["files/protected-1"]
    assert not protected_path.exists()
    assert client.get(f"/api/ai/jobs/{job_id}").status_code == 404


def test_worker_reclaims_stale_running_job(client, pdf_document_id, monkeypatch):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )
    job_id = _enqueue(client, artifact_id).json()["id"]
    with TestingSessionLocal() as db:
        job = db.get(AIAnalysisJob, job_id)
        job.status = "running"
        job.stage = "analyzing"
        job.started_at = utc_now() - timedelta(seconds=301)
        db.commit()

    assert run_next_ai_job(TestingSessionLocal) is True
    result = client.get(f"/api/ai/jobs/{job_id}").json()
    assert result["status"] == "completed"
    assert result["attempts"] == 1


def test_pending_ai_job_can_be_cancelled(client, pdf_document_id):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    job_id = _enqueue(client, artifact_id).json()["id"]

    response = client.post(f"/api/ai/jobs/{job_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert run_next_ai_job(TestingSessionLocal) is False


def test_artifact_is_kept_when_remote_cleanup_fails(
    client, pdf_document_id, monkeypatch
):
    artifact_id, protected_path, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )
    job_id = _enqueue(client, artifact_id, retention="retain_48h").json()["id"]
    assert run_next_ai_job(TestingSessionLocal) is True
    provider.fail_delete = True

    response = client.delete(f"/api/tools/artifacts/{artifact_id}")

    assert response.status_code == 502
    assert protected_path.exists()
    assert client.get(f"/api/tools/artifacts/{artifact_id}").status_code == 200
    persisted = client.get(f"/api/ai/jobs/{job_id}")
    assert persisted.status_code == 200
    assert persisted.json()["remote_cleanup_status"] == "failed"
    assert persisted.json()["remote_cleanup_error"]
    assert "could not be deleted" in persisted.json()["public_error"]


def test_provider_file_processing_has_a_bounded_deadline(
    client, pdf_document_id, monkeypatch
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    provider.remote = AIRemoteDocument(
        name=provider.remote.name,
        uri=provider.remote.uri,
        mime_type=provider.remote.mime_type,
        state="PROCESSING",
        expires_at=provider.remote.expires_at,
    )
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )
    extraction_calls = []

    def unexpected_extraction(*args, **kwargs):
        extraction_calls.append((args, kwargs))
        raise AssertionError("OCR must wait until the provider file is active")

    monkeypatch.setattr(
        "app.services.ai.jobs.extract_pdf_pages_with_ocr",
        unexpected_extraction,
    )
    job_id = _enqueue(client, artifact_id).json()["id"]

    assert run_next_ai_job(TestingSessionLocal) is True
    assert client.get(f"/api/ai/jobs/{job_id}").json()["status"] == "retry_scheduled"
    with TestingSessionLocal() as db:
        job = db.get(AIAnalysisJob, job_id)
        job.not_before = utc_now() - timedelta(seconds=1)
        job.provider_file_processing_started_at = utc_now() - timedelta(seconds=121)
        db.commit()

    assert run_next_ai_job(TestingSessionLocal) is True
    result = client.get(f"/api/ai/jobs/{job_id}").json()
    assert result["status"] == "failed"
    assert result["error_code"] == "analysis_failed"
    assert provider.deleted == ["files/protected-1"]
    assert extraction_calls == []


def test_cache_does_not_reuse_a_job_with_different_retention_policy(
    client, pdf_document_id, monkeypatch
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )
    retained_id = _enqueue(
        client,
        artifact_id,
        task="content_review",
        retention="retain_48h",
    ).json()["id"]
    assert run_next_ai_job(TestingSessionLocal) is True

    one_shot = _enqueue(
        client,
        artifact_id,
        task="content_review",
        retention="delete_after_analysis",
    )

    assert one_shot.status_code == 202
    assert one_shot.json()["id"] != retained_id
    assert one_shot.json()["retention"] == "delete_after_analysis"
    assert one_shot.json()["status"] == "pending"


def test_one_shot_cleanup_failure_is_visible_and_can_be_retried(
    client, pdf_document_id, monkeypatch
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    provider.remote = AIRemoteDocument(
        name=provider.remote.name,
        uri=provider.remote.uri,
        mime_type=provider.remote.mime_type,
        state="ACTIVE",
        expires_at=None,
    )
    provider.fail_delete = True
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )
    job_id = _enqueue(client, artifact_id).json()["id"]

    assert run_next_ai_job(TestingSessionLocal) is True
    completed = client.get(f"/api/ai/jobs/{job_id}").json()
    assert completed["status"] == "completed"
    assert completed["remote_file_present"] is True
    assert completed["provider_file_expires_at"] is None
    assert completed["remote_cleanup_status"] == "failed"
    assert completed["remote_cleanup_error"]
    assert "could not be deleted" in completed["public_error"]

    provider.fail_delete = False
    deleted = client.delete(f"/api/ai/jobs/{job_id}/remote-file")
    assert deleted.status_code == 200
    assert deleted.json()["remote_file_present"] is False
    assert deleted.json()["remote_cleanup_status"] == "deleted"
    assert deleted.json()["public_error"] is None
    assert deleted.json()["error_code"] is None
    with TestingSessionLocal() as db:
        assert db.get(AIAnalysisJob, job_id).private_error is None


def test_stale_cancelled_worker_is_reconciled_before_claiming_more_work(
    client, pdf_document_id, monkeypatch
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )
    job_id = _enqueue(client, artifact_id, retention="retain_48h").json()["id"]
    with TestingSessionLocal() as db:
        job = db.get(AIAnalysisJob, job_id)
        job.status = "running"
        job.worker_active = True
        job.started_at = utc_now() - timedelta(seconds=301)
        job.provider_file_name = provider.remote.name
        job.provider_file_uri = provider.remote.uri
        job.provider_file_expires_at = provider.remote.expires_at
        job.remote_cleanup_status = "retained"
        db.commit()

    cancelled = client.post(f"/api/ai/jobs/{job_id}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["worker_active"] is True
    assert run_next_ai_job(TestingSessionLocal) is False
    reconciled = client.get(f"/api/ai/jobs/{job_id}").json()
    assert reconciled["status"] == "cancelled"
    assert reconciled["worker_active"] is False
    assert reconciled["remote_file_present"] is False
    assert provider.deleted == [provider.remote.name]
    assert client.delete(f"/api/tools/artifacts/{artifact_id}").status_code == 204


def test_running_worker_observes_cancel_and_deletes_its_remote_copy(
    client, pdf_document_id, monkeypatch
):
    artifact_id, _, _ = _create_artifact(pdf_document_id)
    provider = FakeDocumentProvider()
    monkeypatch.setattr(
        "app.services.ai.jobs.get_ai_provider", lambda: provider
    )
    job_id = _enqueue(client, artifact_id).json()["id"]
    with TestingSessionLocal() as db:
        job = db.get(AIAnalysisJob, job_id)
        job.status = "running"
        job.worker_active = True
        job.started_at = utc_now()
        job.provider_file_name = provider.remote.name
        job.provider_file_uri = provider.remote.uri
        job.provider_file_expires_at = provider.remote.expires_at
        job.remote_cleanup_status = "pending"
        db.commit()

    cancelled = client.post(f"/api/ai/jobs/{job_id}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["worker_active"] is True
    with TestingSessionLocal() as db:
        job = db.get(AIAnalysisJob, job_id)
        assert _stop_cancelled_job(db, job, provider) is True

    stopped = client.get(f"/api/ai/jobs/{job_id}").json()
    assert stopped["status"] == "cancelled"
    assert stopped["worker_active"] is False
    assert stopped["remote_file_present"] is False
    assert provider.deleted == [provider.remote.name]


def test_active_ai_job_blocks_artifact_deletion_until_cancelled(
    client, pdf_document_id
):
    artifact_id, protected_path, _ = _create_artifact(pdf_document_id)
    job_id = _enqueue(client, artifact_id).json()["id"]

    blocked = client.delete(f"/api/tools/artifacts/{artifact_id}")

    assert blocked.status_code == 409
    assert protected_path.exists()
    assert client.post(f"/api/ai/jobs/{job_id}/cancel").status_code == 200
    assert client.delete(f"/api/tools/artifacts/{artifact_id}").status_code == 204
    assert not protected_path.exists()
