from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path

import pymupdf
from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import create_session
from app.models._utils import utc_now
from app.models.ai_analysis_job import AIAnalysisJob
from app.models.document_artifact import DocumentArtifact
from app.schemas.ai_analysis import AIAnalysisJobCreate
from app.services.ai_document_analysis import (
    ProtectedDocumentAnalysisError,
    analyze_protected_document,
)
from app.services.ai_provider import (
    AIDocument,
    AIProviderError,
    AIRemoteDocument,
    get_ai_provider,
)
from app.services.document_artifacts import require_ai_ready_artifact
from app.services.text_analysis import OCRExtractionError, extract_pdf_pages_with_ocr

SessionFactory = Callable[[], Session]
PROMPT_VERSION = "protected-v1"
SCHEMA_VERSION = "analysis-v1"
REMOTE_CLEANUP_WARNING = (
    "The external AI copy could not be deleted; use "
    "'delete external copy' to retry."
)
GEMINI_PROVIDER_TERMS_URL = "https://ai.google.dev/gemini-api/terms"
DEDUPLICATED_STATUSES = {"pending", "running", "retry_scheduled", "completed"}


class AIAnalysisJobError(RuntimeError):
    pass


class AIAnalysisConsentRequired(AIAnalysisJobError):
    pass


class AIAnalysisJobNotCancellable(AIAnalysisJobError):
    pass


class AIAnalysisJobsActive(AIAnalysisJobError):
    pass


def enqueue_ai_analysis(
    db: Session,
    *,
    user_id: int,
    payload: AIAnalysisJobCreate,
) -> AIAnalysisJob:
    if not payload.consent_to_external_processing:
        raise AIAnalysisConsentRequired("External AI processing consent is required")
    if not payload.acknowledge_provider_data_terms:
        raise AIAnalysisConsentRequired("Provider data terms must be acknowledged")

    # Expired provider objects are no longer reusable and must not remain visible
    # as external copies. Reconcile before acquiring the artifact row lock so the
    # lock remains held through the deduplicated insert below.
    reconcile_expired_remote_files(db, user_id=user_id)
    artifact = require_ai_ready_artifact(db, payload.artifact_id, user_id)
    provider_name = settings.ai_provider
    service_tier = getattr(settings, "gemini_service_tier", "unpaid")
    requested_model = (
        settings.gemini_model if provider_name.strip().lower() == "gemini" else None
    )
    dedupe_key = _build_dedupe_key(
        user_id=user_id,
        artifact_id=artifact.id,
        artifact_sha256=artifact.artifact_sha256,
        task=payload.task,
        provider=provider_name,
        model=requested_model,
        service_tier=service_tier,
        retention=payload.retention,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
    )
    existing = db.scalar(
        select(AIAnalysisJob)
        .where(
            AIAnalysisJob.dedupe_key == dedupe_key,
            AIAnalysisJob.status.in_(DEDUPLICATED_STATUSES),
        )
        .order_by(AIAnalysisJob.created_at.desc(), AIAnalysisJob.id.desc())
        .limit(1)
    )
    if existing is not None:
        return existing

    job = AIAnalysisJob(
        user_id=user_id,
        artifact_id=artifact.id,
        task=payload.task,
        provider=provider_name,
        model=requested_model,
        artifact_sha256=artifact.artifact_sha256,
        dedupe_key=dedupe_key,
        retention=payload.retention,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        consent_snapshot={
            "external_processing": True,
            "provider_data_terms_acknowledged": True,
            "provider": provider_name,
            "service_tier": service_tier,
            "artifact_id": artifact.id,
            "artifact_sha256": artifact.artifact_sha256,
            "artifact_policy_version": artifact.policy_version,
            "detector_version": artifact.detector_version,
            "retention": payload.retention,
            "accepted_at": utc_now().isoformat(),
            **(
                {"provider_terms_url": GEMINI_PROVIDER_TERMS_URL}
                if provider_name.strip().lower() == "gemini"
                else {}
            ),
        },
    )
    db.add(job)
    return _commit_deduplicated_job(db, job, dedupe_key)


def reconcile_expired_remote_files(
    db: Session,
    *,
    user_id: int | None = None,
    artifact_ids: list[int] | None = None,
) -> int:
    """Clear all DB references to provider files whose known TTL elapsed."""
    if artifact_ids is not None and not artifact_ids:
        return 0
    filters = [
        AIAnalysisJob.provider_file_name.is_not(None),
        AIAnalysisJob.provider_file_expires_at.is_not(None),
        AIAnalysisJob.provider_file_expires_at <= utc_now(),
    ]
    if user_id is not None:
        filters.append(AIAnalysisJob.user_id == user_id)
    if artifact_ids is not None:
        filters.append(AIAnalysisJob.artifact_id.in_(artifact_ids))
    expired_files = {
        (provider, remote_name)
        for provider, remote_name in db.execute(
            select(
                AIAnalysisJob.provider,
                AIAnalysisJob.provider_file_name,
            ).where(*filters)
        )
        if remote_name
    }
    for provider_name, remote_name in expired_files:
        _clear_remote_references(db, provider_name, remote_name)
    if expired_files:
        db.commit()
    return len(expired_files)


def _build_dedupe_key(
    *,
    user_id: int,
    artifact_id: int,
    artifact_sha256: str,
    task: str,
    provider: str,
    model: str | None,
    service_tier: str,
    retention: str,
    prompt_version: str,
    schema_version: str,
) -> str:
    material = json.dumps(
        {
            "artifact_id": artifact_id,
            "artifact_sha256": artifact_sha256,
            "model": model,
            "prompt_version": prompt_version,
            "provider": provider,
            "retention": retention,
            "schema_version": schema_version,
            "service_tier": service_tier,
            "task": task,
            "user_id": user_id,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(material.encode("utf-8")).hexdigest()


def _commit_deduplicated_job(
    db: Session,
    job: AIAnalysisJob,
    dedupe_key: str,
) -> AIAnalysisJob:
    try:
        db.commit()
    except IntegrityError:
        # Another request committed the same logical enqueue after our lookup.
        # The unique key is the authority; recover idempotently from that row.
        db.rollback()
        existing = db.scalar(
            select(AIAnalysisJob)
            .where(
                AIAnalysisJob.dedupe_key == dedupe_key,
                AIAnalysisJob.status.in_(DEDUPLICATED_STATUSES),
            )
            .limit(1)
        )
        if existing is None:
            raise
        return existing
    db.refresh(job)
    return job


def claim_next_ai_job(db: Session) -> AIAnalysisJob | None:
    now = utc_now()
    stale_before = now - timedelta(
        seconds=int(getattr(settings, "ai_job_stale_seconds", 300))
    )
    _reconcile_stale_cancelled_jobs(db, stale_before)
    job = db.scalar(
        select(AIAnalysisJob)
        .where(
            or_(
                and_(
                    AIAnalysisJob.status.in_({"pending", "retry_scheduled"}),
                    or_(
                        AIAnalysisJob.not_before.is_(None),
                        AIAnalysisJob.not_before <= now,
                    ),
                ),
                and_(
                    AIAnalysisJob.status == "running",
                    AIAnalysisJob.started_at < stale_before,
                ),
            )
        )
        .order_by(AIAnalysisJob.created_at, AIAnalysisJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    reclaimed = job.status == "running"
    job.status = "running"
    job.worker_active = True
    job.stage = "restarting" if reclaimed else "starting"
    job.progress = max(job.progress, 1)
    job.started_at = now
    job.not_before = None
    job.public_error = None
    job.private_error = None
    job.error_code = None
    db.commit()
    db.refresh(job)
    return job


def run_next_ai_job(session_factory: SessionFactory = create_session) -> bool:
    with session_factory() as db:
        job = claim_next_ai_job(db)
        if job is None:
            return False
        job_id = job.id
    process_ai_job(job_id, session_factory=session_factory)
    return True


def process_ai_job(
    job_id: int,
    *,
    session_factory: SessionFactory = create_session,
) -> None:
    with session_factory() as db:
        job = db.get(AIAnalysisJob, job_id)
        if job is None:
            return
        if job.status != "running":
            if job.worker_active:
                job.worker_active = False
                db.commit()
            return
        provider = None
        remote: AIRemoteDocument | None = None
        provider_attempt_recorded = False
        try:
            artifact = require_ai_ready_artifact(db, job.artifact_id, job.user_id)
            if artifact.artifact_sha256 != job.artifact_sha256:
                raise AIAnalysisJobError("Protected artifact version changed")
            path = Path(artifact.stored_path)
            if _stop_cancelled_job(db, job, provider):
                return

            provider = get_ai_provider()
            job.stage = "uploading"
            job.progress = 5
            db.commit()
            reconcile_expired_remote_files(db, user_id=job.user_id)
            reusable = _find_reusable_remote(db, job)
            remote_name = job.provider_file_name or (
                reusable.provider_file_name if reusable is not None else None
            )
            if remote_name:
                try:
                    remote = provider.get_document(remote_name)
                    _store_remote(job, remote)
                    db.commit()
                except AIProviderError as error:
                    if error.code != 404:
                        raise
                    _clear_remote_references(db, job.provider, remote_name)
                    db.commit()
            if remote is None:
                job.attempts += 1
                provider_attempt_recorded = True
                db.commit()
                remote = provider.upload_document(
                    AIDocument(
                        path=path,
                        mime_type=artifact.content_type,
                        display_name=f"protected-{artifact.id}.pdf",
                    )
                )
                _store_remote(job, remote)
                db.commit()

            if _stop_cancelled_job(db, job, provider):
                return
            if remote.state == "PROCESSING":
                processing_started = (
                    job.provider_file_processing_started_at or utc_now()
                )
                if processing_started.tzinfo is None:
                    processing_started = processing_started.replace(tzinfo=timezone.utc)
                processing_timeout = int(
                    getattr(settings, "ai_file_processing_timeout_seconds", 120)
                )
                if utc_now() >= processing_started + timedelta(
                    seconds=processing_timeout
                ):
                    raise AIAnalysisJobError(
                        "AI provider document processing timed out"
                    )
                job.status = "retry_scheduled"
                job.worker_active = False
                job.stage = "provider_processing"
                job.progress = 20
                job.not_before = utc_now() + timedelta(seconds=2)
                db.commit()
                return
            if remote.state != "ACTIVE":
                raise AIAnalysisJobError("AI provider could not process protected PDF")
            job.provider_file_processing_started_at = None

            if not _reserve_provider_request(db, job):
                return
            job.stage = "indexing_protected_copy"
            job.progress = max(job.progress, 25)
            db.commit()

            def extraction_heartbeat(
                completed_pages: int,
                total_pages: int,
                _stage: str,
            ) -> None:
                job.started_at = utc_now()
                job.progress = max(
                    job.progress,
                    25
                    + int(
                        (max(0, completed_pages) / max(total_pages, 1))
                        * 15
                    ),
                )
                db.commit()

            page_texts = _page_texts(
                path,
                progress_callback=extraction_heartbeat,
            )
            if _stop_cancelled_job(db, job, provider):
                return
            if not provider_attempt_recorded:
                job.attempts += 1
                provider_attempt_recorded = True
            job.stage = "analyzing"
            job.progress = 45
            db.commit()
            result, model, usage = analyze_protected_document(
                provider,
                remote,
                task=job.task,
                page_texts=page_texts,
            )
            if _stop_cancelled_job(db, job, provider):
                return
            job.result = result.model_dump(mode="json")
            job.model = model
            job.usage = usage or {}
            job.status = "completed"
            job.worker_active = False
            job.stage = "completed"
            job.progress = 100
            job.finished_at = utc_now()
            job.public_error = None
            job.private_error = None
            job.error_code = None
            if job.retention == "delete_after_analysis":
                _delete_remote_best_effort(db, provider, job)
            db.commit()
        except AIProviderError as error:
            if _stop_cancelled_job(db, job, provider):
                return
            _handle_provider_error(
                db,
                job,
                error,
                provider,
                attempt_recorded=provider_attempt_recorded,
            )
        except (AIAnalysisJobError, ProtectedDocumentAnalysisError) as error:
            if _stop_cancelled_job(db, job, provider):
                return
            _fail_job(db, job, "analysis_failed", str(error), provider)
        except Exception as error:
            if _stop_cancelled_job(db, job, provider):
                return
            _fail_job(
                db,
                job,
                "internal_error",
                "Protected document analysis failed",
                provider,
                private_error=str(error),
            )


def delete_remote_copy(db: Session, job: AIAnalysisJob) -> AIAnalysisJob:
    reconcile_expired_remote_files(db, user_id=job.user_id)
    if not job.provider_file_name:
        db.refresh(job)
        return job
    if _remote_file_has_active_jobs(db, job.provider, job.provider_file_name):
        raise AIAnalysisJobsActive(
            "Cancel active AI analysis before deleting the external copy"
        )
    provider = get_ai_provider()
    remote_name = job.provider_file_name
    try:
        provider.delete_document(remote_name)
    except AIProviderError as error:
        if error.code != 404:
            job.remote_cleanup_status = "failed"
            job.remote_cleanup_error = "External AI copy deletion failed; retry is available"
            db.commit()
            raise
    _clear_remote_references(db, job.provider, remote_name)
    db.commit()
    db.refresh(job)
    return job


def cancel_ai_job(db: Session, job: AIAnalysisJob) -> AIAnalysisJob:
    reconcile_expired_remote_files(db, user_id=job.user_id)
    if job.status in {"completed", "failed"}:
        raise AIAnalysisJobNotCancellable("Finished AI analysis cannot be cancelled")
    if job.status != "cancelled":
        job.status = "cancelled"
        job.stage = "cancelled"
        job.finished_at = utc_now()
        job.not_before = None
        job.public_error = None
        job.private_error = None
        job.error_code = None
    job.dedupe_key = None
    db.commit()
    if (
        job.provider_file_name
        and not _remote_file_has_active_jobs(
            db,
            job.provider,
            job.provider_file_name,
        )
    ):
        delete_remote_copy(db, job)
    db.refresh(job)
    return job


def delete_ai_jobs_for_artifacts(db: Session, artifact_ids: list[int]) -> None:
    """Revoke provider files before removing local artifact lineage and job records."""
    if not artifact_ids:
        return
    reconcile_expired_remote_files(db, artifact_ids=artifact_ids)
    # enqueue_ai_analysis locks the same artifact row through
    # require_ai_ready_artifact. This makes enqueue/dedupe and deletion
    # mutually exclusive on PostgreSQL, preventing a job from appearing after
    # the cleanup scan but before the artifact is removed.
    list(
        db.scalars(
            select(DocumentArtifact.id)
            .where(DocumentArtifact.id.in_(artifact_ids))
            .order_by(DocumentArtifact.id)
            .with_for_update()
        )
    )
    jobs = list(
        db.scalars(
            select(AIAnalysisJob).where(AIAnalysisJob.artifact_id.in_(artifact_ids))
        )
    )
    if any(
        job.worker_active
        or job.status in {"pending", "running", "retry_scheduled"}
        for job in jobs
    ):
        raise AIAnalysisJobsActive(
            "Cancel active AI analysis before deleting the protected artifact"
        )
    remote_files = {
        (job.provider, job.provider_file_name)
        for job in jobs
        if job.provider_file_name
    }
    for provider_name, remote_name in remote_files:
        if _remote_file_has_active_jobs(db, provider_name, remote_name):
            raise AIAnalysisJobsActive(
                "Cancel active AI analysis before deleting the protected artifact"
            )
    for provider_name, remote_name in remote_files:
        if provider_name != settings.ai_provider:
            _mark_remote_cleanup_failed_for_references(
                db,
                provider_name,
                remote_name,
                AIAnalysisJobError(
                    f"AI provider '{provider_name}' is unavailable for remote cleanup"
                ),
            )
            db.commit()
            raise AIAnalysisJobError(
                f"AI provider '{provider_name}' is unavailable for remote cleanup"
            )
        provider = get_ai_provider()
        try:
            provider.delete_document(remote_name)
        except AIProviderError as error:
            if error.code != 404:
                _mark_remote_cleanup_failed_for_references(
                    db,
                    provider_name,
                    remote_name,
                    error,
                )
                db.commit()
                raise
        _clear_remote_references(db, provider_name, remote_name)
    db.execute(delete(AIAnalysisJob).where(AIAnalysisJob.artifact_id.in_(artifact_ids)))


def _reserve_provider_request(db: Session, job: AIAnalysisJob) -> bool:
    now = utc_now()
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:quota_key))"),
            {"quota_key": f"protected-ai:{job.provider}:{job.model or ''}"},
        )
    last_request = db.scalar(
        select(func.max(AIAnalysisJob.provider_requested_at)).where(
            AIAnalysisJob.provider == job.provider,
            AIAnalysisJob.model == job.model,
        )
    )
    minimum_interval = max(
        int(getattr(settings, "ai_provider_min_request_interval_seconds", 12)),
        0,
    )
    if last_request is not None:
        if last_request.tzinfo is None:
            last_request = last_request.replace(tzinfo=timezone.utc)
        available_at = last_request + timedelta(seconds=minimum_interval)
        if available_at > now:
            job.status = "retry_scheduled"
            job.worker_active = False
            job.stage = "quota_wait"
            job.not_before = available_at
            job.progress = max(job.progress, 35)
            db.commit()
            return False
    job.provider_requested_at = now
    db.commit()
    return True


def _handle_provider_error(
    db: Session,
    job: AIAnalysisJob,
    error: AIProviderError,
    provider,
    *,
    attempt_recorded: bool,
) -> None:
    if not attempt_recorded:
        job.attempts += 1
    max_attempts = int(getattr(settings, "ai_job_max_attempts", 4))
    if error.retryable and job.attempts < max_attempts:
        base_delay = int(getattr(settings, "ai_retry_base_seconds", 5))
        delay = error.retry_after_seconds or min(base_delay * (2 ** (job.attempts - 1)), 60)
        job.status = "retry_scheduled"
        job.worker_active = False
        job.stage = "retry_wait"
        job.not_before = utc_now() + timedelta(seconds=max(delay, 1))
        job.error_code = str(error.code or "provider_transient")
        job.public_error = "AI provider is temporarily busy; retry scheduled"
        job.private_error = error.provider_detail or str(error)
        db.commit()
        return
    _fail_job(
        db,
        job,
        str(error.code or "provider_error"),
        "AI provider could not complete the protected document analysis",
        provider,
        private_error=error.provider_detail or str(error),
    )


def _fail_job(
    db: Session,
    job: AIAnalysisJob,
    code: str,
    public_error: str,
    provider,
    *,
    private_error: str | None = None,
) -> None:
    job.status = "failed"
    job.dedupe_key = None
    job.worker_active = False
    job.stage = "failed"
    job.error_code = code
    job.public_error = public_error
    job.private_error = private_error or public_error
    job.finished_at = utc_now()
    if provider is not None:
        _delete_remote_best_effort(db, provider, job)
    db.commit()


def _store_remote(job: AIAnalysisJob, remote: AIRemoteDocument) -> None:
    if job.provider_file_name != remote.name:
        job.provider_file_processing_started_at = utc_now()
    job.provider_file_name = remote.name
    job.provider_file_uri = remote.uri
    job.provider_file_expires_at = remote.expires_at
    job.remote_cleanup_status = (
        "retained" if job.retention == "retain_48h" else "pending"
    )
    job.remote_cleanup_error = None


def _clear_remote(job: AIAnalysisJob) -> None:
    job.provider_file_name = None
    job.provider_file_uri = None
    job.provider_file_expires_at = None
    job.provider_file_processing_started_at = None
    job.remote_cleanup_status = "deleted"
    job.remote_cleanup_error = None
    job.public_error = _without_cleanup_warning(job.public_error)
    if job.error_code == "remote_delete_failed":
        job.error_code = None
    if job.private_error and job.private_error.startswith("Remote cleanup failed:"):
        job.private_error = None


def _clear_remote_references(
    db: Session,
    provider_name: str,
    remote_name: str,
) -> None:
    jobs = db.scalars(
        select(AIAnalysisJob).where(
            AIAnalysisJob.provider == provider_name,
            AIAnalysisJob.provider_file_name == remote_name,
        )
    )
    for linked_job in jobs:
        _clear_remote(linked_job)


def _remote_file_has_active_jobs(
    db: Session,
    provider_name: str,
    remote_name: str,
) -> bool:
    return (
        db.scalar(
            select(AIAnalysisJob.id)
            .where(
                AIAnalysisJob.provider == provider_name,
                AIAnalysisJob.provider_file_name == remote_name,
                or_(
                    AIAnalysisJob.worker_active.is_(True),
                    AIAnalysisJob.status.in_(
                        {"pending", "running", "retry_scheduled"}
                    ),
                ),
            )
            .limit(1)
        )
        is not None
    )


def _find_reusable_remote(
    db: Session,
    job: AIAnalysisJob,
) -> AIAnalysisJob | None:
    if job.retention != "retain_48h":
        return None
    now = utc_now()
    return db.scalar(
        select(AIAnalysisJob)
        .where(
            AIAnalysisJob.id != job.id,
            AIAnalysisJob.user_id == job.user_id,
            AIAnalysisJob.artifact_sha256 == job.artifact_sha256,
            AIAnalysisJob.provider == job.provider,
            AIAnalysisJob.retention == "retain_48h",
            AIAnalysisJob.provider_file_name.is_not(None),
            or_(
                AIAnalysisJob.provider_file_expires_at.is_(None),
                AIAnalysisJob.provider_file_expires_at > now,
            ),
        )
        .order_by(AIAnalysisJob.created_at.desc(), AIAnalysisJob.id.desc())
        .limit(1)
    )


def _delete_remote_best_effort(db: Session, provider, job: AIAnalysisJob) -> None:
    if not job.provider_file_name:
        return
    remote_name = job.provider_file_name
    # Sessions intentionally run with autoflush disabled. Persist the terminal
    # status / released worker lease before checking all linked rows.
    db.flush()
    if _remote_file_has_active_jobs(db, job.provider, remote_name):
        return
    try:
        provider.delete_document(remote_name)
    except AIProviderError as error:
        if error.code == 404:
            _clear_remote_references(db, job.provider, remote_name)
            return
        _record_remote_cleanup_failure(job, error)
        return
    except Exception as error:
        _record_remote_cleanup_failure(job, error)
        return
    _clear_remote_references(db, job.provider, remote_name)


def _with_cleanup_warning(existing: str | None) -> str:
    return (
        f"{existing} {REMOTE_CLEANUP_WARNING}"
        if existing
        else REMOTE_CLEANUP_WARNING
    )


def _without_cleanup_warning(existing: str | None) -> str | None:
    if not existing:
        return None
    cleaned = existing.replace(REMOTE_CLEANUP_WARNING, "").strip()
    return cleaned or None


def _record_remote_cleanup_failure(job: AIAnalysisJob, error: Exception) -> None:
    job.error_code = job.error_code or "remote_delete_failed"
    if not job.private_error:
        job.private_error = f"Remote cleanup failed: {error}"
    job.public_error = _with_cleanup_warning(job.public_error)
    job.remote_cleanup_status = "failed"
    job.remote_cleanup_error = "External AI copy deletion failed"


def _mark_remote_cleanup_failed_for_references(
    db: Session,
    provider_name: str,
    remote_name: str,
    error: Exception,
) -> None:
    linked_jobs = db.scalars(
        select(AIAnalysisJob).where(
            AIAnalysisJob.provider == provider_name,
            AIAnalysisJob.provider_file_name == remote_name,
        )
    )
    for linked_job in linked_jobs:
        _record_remote_cleanup_failure(linked_job, error)


def _reconcile_stale_cancelled_jobs(db: Session, stale_before) -> None:
    stale_jobs = list(
        db.scalars(
            select(AIAnalysisJob).where(
                AIAnalysisJob.status == "cancelled",
                AIAnalysisJob.worker_active.is_(True),
                AIAnalysisJob.started_at.is_not(None),
                AIAnalysisJob.started_at < stale_before,
            )
        )
    )
    for stale_job in stale_jobs:
        stale_job.worker_active = False
        if not stale_job.provider_file_name:
            continue
        if stale_job.provider != settings.ai_provider:
            _record_remote_cleanup_failure(
                stale_job,
                AIAnalysisJobError(
                    f"AI provider '{stale_job.provider}' is unavailable for remote cleanup"
                ),
            )
            continue
        try:
            provider = get_ai_provider()
        except Exception as error:
            _record_remote_cleanup_failure(stale_job, error)
            continue
        _delete_remote_best_effort(db, provider, stale_job)
    if stale_jobs:
        db.commit()


def _stop_cancelled_job(db: Session, job: AIAnalysisJob, provider) -> bool:
    db.refresh(job)
    if job.status != "cancelled":
        return False
    job.worker_active = False
    if provider is not None and job.provider_file_name:
        _delete_remote_best_effort(db, provider, job)
    db.commit()
    return True


def _page_texts(path: Path, *, progress_callback=None) -> list[str]:
    try:
        extracted = extract_pdf_pages_with_ocr(
            path,
            progress_callback=progress_callback,
        )
        if extracted:
            return [page.text for page in extracted]
    except OCRExtractionError:
        pass
    try:
        with pymupdf.open(path) as document:
            return [page.get_text("text", sort=True) or "" for page in document]
    except Exception as error:
        raise AIAnalysisJobError("Protected PDF could not be read") from error
