from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import create_session
from app.models._utils import utc_now
from app.models.tool_job import ToolJob
from app.services import document_artifacts, document_redaction, document_tools

SessionFactory = Callable[[], Session]


def claim_next_job(db: Session) -> ToolJob | None:
    job = db.scalar(
        select(ToolJob)
        .where(ToolJob.status == "pending")
        .order_by(ToolJob.created_at, ToolJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = "running"
    job.stage = "starting"
    job.progress = max(job.progress, 1)
    job.started_at = utc_now()
    job.finished_at = None
    job.error_message = None
    db.commit()
    db.refresh(job)
    return job


def run_next_tool_job(session_factory: SessionFactory = create_session) -> bool:
    with session_factory() as db:
        job = claim_next_job(db)
        if job is None:
            return False
        job_id = job.id
    process_tool_job(job_id, session_factory=session_factory)
    return True


def process_tool_job(
    job_id: int,
    *,
    session_factory: SessionFactory = create_session,
) -> None:
    with session_factory() as db:
        job = db.get(ToolJob, job_id)
        if job is None or job.status != "running":
            return

        def update_progress(percent: int, stage: str) -> None:
            job.progress = percent
            job.stage = stage
            db.commit()

        try:
            source = Path(job.source_path)
            if not source.is_file():
                raise document_tools.DocumentToolError("Source document no longer exists")
            if job.kind == "compression":
                destination = _result_path(job, ".pdf")
                meta = document_tools.compress_pdf(
                    source,
                    destination,
                    str(job.options.get("mode", "recommended")),
                    update_progress,
                )
                _complete(job, destination, "application/pdf", meta)
            elif job.kind == "word_to_pdf":
                destination = _result_path(job, ".pdf")
                meta = document_tools.word_to_pdf(source, destination, update_progress)
                _complete(job, destination, "application/pdf", meta)
            elif job.kind == "pdf_to_word":
                destination = _result_path(job, ".docx")
                meta = document_tools.pdf_to_word(source, destination, update_progress)
                _complete(
                    job,
                    destination,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    meta,
                )
            elif job.kind == "redaction":
                _process_redaction(db, job, source, update_progress)
            else:
                raise document_tools.DocumentToolError("Unknown tool job")
            db.commit()
        except Exception as error:
            job.status = "failed"
            job.stage = "failed"
            job.error_message = str(error)
            job.finished_at = utc_now()
            db.commit()


def _process_redaction(db: Session, job: ToolJob, source: Path, progress) -> None:
    operation = job.options.get("operation", "preview")
    if operation == "preview":
        findings, meta = document_redaction.detect_redactions(
            source,
            set(job.options.get("categories", ["personal", "financial"])),
            progress,
        )
        job.findings = findings
        job.result_meta = meta
        job.status = "review"
        job.stage = "review"
        job.progress = 100
        job.finished_at = utc_now()
        return
    destination = _result_path(job, ".pdf", suffix="-protected")
    preview_meta = dict(job.result_meta)
    selected_areas = job.options.get("selected_redaction_areas", [])
    findings = (
        document_redaction.findings_from_areas(source, job.findings, selected_areas)
        if selected_areas
        else job.findings
    )
    categories = set(job.options.get("categories", ["personal", "financial"]))
    redaction_mode = str(job.options.get("redaction_mode", "black"))
    selected_ids = set(job.options.get("selected_finding_ids", []))
    selected_findings = [
        finding for finding in findings if finding.get("id") in selected_ids
    ]

    def redaction_progress(percent: int, stage: str) -> None:
        progress(min(85, int(max(0, min(percent, 100)) * 0.85)), stage)

    try:
        meta = document_redaction.apply_redactions(
            source,
            destination,
            findings,
            selected_ids,
            redaction_mode,
            redaction_progress,
        )
        progress(86, "verifying")
        artifact = document_artifacts.register_protected_artifact(
            db,
            job=job,
            source=source,
            result=destination,
            categories=categories,
            redaction_mode=redaction_mode,
            selected_finding_count=len(selected_findings),
            preview_meta=preview_meta,
            generation_meta=meta,
        )
        job.result_artifact_id = artifact.id
        job.result_path = str(destination.resolve())
        job.result_filename = destination.name
        job.result_content_type = "application/pdf"
        job.result_size_bytes = destination.stat().st_size
        job.findings = document_artifacts.minimize_findings(job.findings)
        db.commit()

        try:
            artifact_status, coverage, verification = (
                document_artifacts.verify_protected_artifact(
                    artifact,
                    selected_findings=selected_findings,
                    progress=progress,
                )
            )
            document_artifacts.complete_artifact_verification(
                artifact,
                status=artifact_status,
                coverage_report=coverage,
                verification_report=verification,
            )
        except Exception as error:
            document_artifacts.fail_artifact_verification(artifact, error)
            db.commit()
            raise

        _complete(
            job,
            destination,
            "application/pdf",
            {
                **meta,
                "artifact_status": artifact.status,
                "verification": artifact.verification_report,
            },
        )
    except Exception:
        if job.result_artifact_id is None:
            destination.unlink(missing_ok=True)
        raise


def _complete(job: ToolJob, destination: Path, content_type: str, meta: dict) -> None:
    job.status = "completed"
    job.stage = "completed"
    job.progress = 100
    job.result_path = str(destination.resolve())
    job.result_filename = destination.name
    job.result_content_type = content_type
    job.result_size_bytes = destination.stat().st_size
    job.result_meta = meta
    job.error_message = None
    job.finished_at = utc_now()


def _result_path(job: ToolJob, extension: str, suffix: str = "") -> Path:
    directory = Path(settings.storage_dir).parent / "tools" / "results" / str(job.user_id)
    directory.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "-", Path(job.source_filename).stem, flags=re.UNICODE).strip(".-")
    label = {
        "compression": "-compressed",
        "word_to_pdf": "",
        "pdf_to_word": "-editable",
    }.get(job.kind, suffix)
    return directory / f"{stem or 'document'}{label}-{job.id}{extension}"
