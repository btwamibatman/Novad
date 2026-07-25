from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import create_session
from app.crud import document as document_crud
from app.models._utils import utc_now
from app.models.analysis_job import AnalysisJob
from app.models.document import Document
from app.services.document_chunks import (
    build_document_chunks,
    language_distribution,
    primary_language,
)
from app.services.text_analysis import (
    analyze_text,
    assess_extraction_quality,
    extract_text_pages,
    join_page_text,
)


def enqueue_analysis(db: Session, document: Document) -> Document:
    job = db.scalar(
        select(AnalysisJob).where(AnalysisJob.document_id == document.id)
    )
    if job and job.status in {"pending", "running"}:
        document.status = "analyzing"
        if not document.analysis_progress:
            document.analysis_progress = {
                "stage": "queued",
                "completed_pages": 0,
                "total_pages": None,
            }
        db.commit()
        db.refresh(document)
        return document

    if job is None:
        job = AnalysisJob(document_id=document.id)
        db.add(job)
    else:
        job.status = "pending"
        job.error_message = None
        job.created_at = utc_now()
        job.started_at = None
        job.finished_at = None

    document.status = "analyzing"
    document.analysis_progress = {
        "stage": "queued",
        "completed_pages": 0,
        "total_pages": None,
    }
    document.error_message = None
    db.commit()
    db.refresh(document)
    return document


def claim_next_job(db: Session) -> AnalysisJob | None:
    job = db.scalar(
        select(AnalysisJob)
        .where(AnalysisJob.status == "pending")
        .order_by(AnalysisJob.created_at, AnalysisJob.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return None
    job.status = "running"
    job.attempts += 1
    job.started_at = utc_now()
    job.finished_at = None
    db.commit()
    db.refresh(job)
    return job


SessionFactory = Callable[[], Session]


def run_next_analysis_job(
    session_factory: SessionFactory = create_session,
) -> bool:
    with session_factory() as db:
        job = claim_next_job(db)
        if job is None:
            return False
        job_id = job.id

    process_analysis_job(job_id, session_factory=session_factory)
    return True


def process_analysis_job(
    job_id: int,
    *,
    session_factory: SessionFactory = create_session,
) -> None:
    with session_factory() as db:
        job = db.get(AnalysisJob, job_id)
        if job is None or job.status != "running":
            return
        document = db.get(Document, job.document_id)
        if document is None:
            job.status = "failed"
            job.error_message = "Document no longer exists"
            job.finished_at = utc_now()
            db.commit()
            return

        def update_progress(completed_pages: int, total_pages: int, stage: str) -> None:
            document.analysis_progress = {
                "stage": stage,
                "completed_pages": completed_pages,
                "total_pages": total_pages,
            }
            db.commit()

        try:
            extracted_pages = extract_text_pages(
                document,
                progress_callback=update_progress,
            )
            update_progress(len(extracted_pages), len(extracted_pages), "quality")
            extracted_text = join_page_text(extracted_pages).strip()
            if not extracted_text:
                raise ValueError(
                    "OCR failed: no readable text was found after OCR"
                )
            _, word_count, char_count = analyze_text(extracted_text)
            chunks = build_document_chunks(extracted_pages)
            distribution = language_distribution(chunks)
            extraction_quality = assess_extraction_quality(extracted_pages)
            document_crud.update_document_analysis(
                db,
                document,
                status="processed",
                extracted_text=extracted_text,
                extraction_quality=extraction_quality.quality,
                extraction_quality_meta=extraction_quality.meta,
                detected_language=primary_language(distribution),
                language_distribution=distribution,
                word_count=word_count,
                char_count=char_count,
                error_message=None,
                chunks=chunks,
            )
        except Exception as error:
            document_crud.update_document_analysis(
                db,
                document,
                status="failed",
                extracted_text="",
                extraction_quality="unknown",
                extraction_quality_meta={},
                language_distribution={},
                error_message=str(error),
                chunks=[],
            )
            job.status = "failed"
            job.error_message = str(error)
            job.finished_at = utc_now()
            db.commit()
            return

        job.status = "completed"
        job.error_message = None
        job.finished_at = utc_now()
        db.commit()
