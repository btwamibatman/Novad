from app.models.tool_job import ToolJob
from app.models.document_artifact import DocumentArtifact
from tests.conftest import TestingSessionLocal


def queue_job(client, document_id):
    response = client.post(
        "/api/tools/compress", json={"document_id": document_id, "mode": "low"}
    )
    assert response.status_code == 202
    return response.json()["id"]


def test_history_hiding_is_persistent_reversible_and_preserves_download(
    client, other_client, pdf_document_id, tmp_path
):
    job_id = queue_job(client, pdf_document_id)
    result = tmp_path / "compressed.pdf"
    result.write_bytes(b"%PDF-test-result")
    with TestingSessionLocal() as db:
        job = db.get(ToolJob, job_id)
        job.status = "completed"
        job.result_filename = "compressed.pdf"
        job.result_content_type = "application/pdf"
        job.result_path = str(result)
        db.commit()

    assert other_client.patch(
        f"/api/tools/jobs/{job_id}/history", json={"hidden": True}
    ).status_code == 404
    hidden = client.patch(f"/api/tools/jobs/{job_id}/history", json={"hidden": True})
    assert hidden.status_code == 200
    assert hidden.json()["hidden_from_history"] is True
    assert client.get("/api/tools/jobs").json()[0]["hidden_from_history"] is True
    assert client.get(f"/api/tools/jobs/{job_id}/download").content == result.read_bytes()
    restored = client.patch(f"/api/tools/jobs/{job_id}/history", json={"hidden": False})
    assert restored.status_code == 200
    with TestingSessionLocal() as db:
        assert db.get(ToolJob, job_id).hidden_from_history is False


def test_unfinished_tasks_cannot_be_hidden(client, pdf_document_id):
    job_id = queue_job(client, pdf_document_id)
    for state in ["pending", "running", "review"]:
        with TestingSessionLocal() as db:
            db.get(ToolJob, job_id).status = state
            db.commit()
        response = client.patch(f"/api/tools/jobs/{job_id}/history", json={"hidden": True})
        assert response.status_code == 409


def test_task_cannot_be_hidden_during_protected_copy_verification(client, pdf_document_id):
    job_id = queue_job(client, pdf_document_id)
    with TestingSessionLocal() as db:
        job = db.get(ToolJob, job_id)
        artifact = DocumentArtifact(
            user_id=job.user_id, source_document_id=pdf_document_id,
            filename="protected.pdf", content_type="application/pdf", stored_path="unused.pdf",
            size_bytes=100, source_sha256="a" * 64, artifact_sha256="b" * 64,
            policy_version="1", detector_version="test", status="verifying",
        )
        db.add(artifact)
        db.flush()
        job.status = "completed"
        job.result_artifact_id = artifact.id
        db.commit()
    response = client.patch(f"/api/tools/jobs/{job_id}/history", json={"hidden": True})
    assert response.status_code == 409


def test_old_active_task_stays_visible_beyond_recent_history_limit(client, pdf_document_id):
    job_id = queue_job(client, pdf_document_id)
    with TestingSessionLocal() as db:
        source = db.get(ToolJob, job_id)
        for _ in range(55):
            db.add(ToolJob(
                user_id=source.user_id,
                source_document_id=source.source_document_id,
                source_filename=source.source_filename,
                source_content_type=source.source_content_type,
                source_path=source.source_path,
                kind="compression",
                status="completed",
            ))
        db.commit()
    jobs = client.get("/api/tools/jobs").json()
    assert len(jobs) == 51
    assert any(job["id"] == job_id and job["status"] == "pending" for job in jobs)
