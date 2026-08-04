from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_document_or_404
from app.core.database import get_db
from app.models.session import UserSession
from app.models.tool_job import ToolJob
from app.api.deps import get_current_session
from app.schemas.tools import (
    CompressionRequest,
    PdfToWordRequest,
    RedactionApplyRequest,
    RedactionPreviewRequest,
    ToolJobRead,
)
from app.services.document_tools import (
    DocumentToolError,
    render_pdf_page,
    save_word_upload,
)
from app.services.file_storage import resolve_stored_path
from app.services.rate_limit import enforce_rate_limit

router = APIRouter()


@router.get("/jobs", response_model=list[ToolJobRead])
def list_jobs(
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> list[ToolJob]:
    return list(
        db.scalars(
            select(ToolJob)
            .where(ToolJob.user_id == current_session.user_id)
            .order_by(ToolJob.created_at.desc(), ToolJob.id.desc())
            .limit(50)
        )
    )


@router.get("/jobs/{job_id}", response_model=ToolJobRead)
def read_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> ToolJob:
    return _owned_job(db, job_id, current_session.user_id)


@router.post("/compress", response_model=ToolJobRead, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_compression(
    payload: CompressionRequest,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> ToolJob:
    await enforce_rate_limit(f"user:{current_session.user_id}", "document-tools", limit=10)
    document = _pdf_document(db, payload.document_id, current_session.user_id)
    return _create_job(
        db,
        user_id=current_session.user_id,
        source_document_id=document.id,
        kind="compression",
        filename=document.filename,
        content_type=document.content_type,
        path=str(resolve_stored_path(document.stored_path).resolve()),
        options={"mode": payload.mode},
    )


@router.post("/word-to-pdf", response_model=ToolJobRead, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_word_to_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> ToolJob:
    await enforce_rate_limit(f"user:{current_session.user_id}", "document-tools", limit=10)
    try:
        filename, content_type, path = await save_word_upload(file)
    except DocumentToolError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    try:
        return _create_job(
            db,
            user_id=current_session.user_id,
            source_document_id=None,
            kind="word_to_pdf",
            filename=filename,
            content_type=content_type,
            path=path,
            options={},
        )
    except Exception:
        Path(path).unlink(missing_ok=True)
        raise


@router.post("/pdf-to-word", response_model=ToolJobRead, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_pdf_to_word(
    payload: PdfToWordRequest,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> ToolJob:
    await enforce_rate_limit(f"user:{current_session.user_id}", "document-tools", limit=10)
    document = _pdf_document(db, payload.document_id, current_session.user_id)
    return _create_job(
        db,
        user_id=current_session.user_id,
        source_document_id=document.id,
        kind="pdf_to_word",
        filename=document.filename,
        content_type=document.content_type,
        path=str(resolve_stored_path(document.stored_path).resolve()),
        options={"ocr_for_scans": True, "beta": True},
    )


@router.post("/redaction/preview", response_model=ToolJobRead, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_redaction_preview(
    payload: RedactionPreviewRequest,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> ToolJob:
    await enforce_rate_limit(f"user:{current_session.user_id}", "document-tools", limit=10)
    document = _pdf_document(db, payload.document_id, current_session.user_id)
    categories = list(dict.fromkeys(payload.categories))
    if not categories:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose at least one category")
    return _create_job(
        db,
        user_id=current_session.user_id,
        source_document_id=document.id,
        kind="redaction",
        filename=document.filename,
        content_type=document.content_type,
        path=str(resolve_stored_path(document.stored_path).resolve()),
        options={"operation": "preview", "categories": categories},
    )


@router.post("/jobs/{job_id}/apply-redaction", response_model=ToolJobRead, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_redaction_apply(
    job_id: int,
    payload: RedactionApplyRequest,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> ToolJob:
    await enforce_rate_limit(f"user:{current_session.user_id}", "document-tools", limit=10)
    job = _owned_job(db, job_id, current_session.user_id)
    if job.kind != "redaction" or job.status != "review":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Redaction preview is not ready")
    selected_areas = [area.model_dump() for area in payload.areas]
    if selected_areas:
        page_count = int(job.result_meta.get("page_count", 0))
        area_ids = [area["id"] for area in selected_areas]
        invalid_area = any(
            area["page"] > page_count
            or area["rect"]["x"] + area["rect"]["width"] > 100.001
            or area["rect"]["y"] + area["rect"]["height"] > 100.001
            for area in selected_areas
        )
        if invalid_area or len(area_ids) != len(set(area_ids)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid redaction areas")
        selected = area_ids
    else:
        available = {finding.get("id") for finding in job.findings}
        selected = list(dict.fromkeys(payload.finding_ids))
        if not selected or any(finding_id not in available for finding_id in selected):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid redaction selection")
    job.options = {
        **job.options,
        "operation": "apply",
        "selected_finding_ids": selected,
        "selected_redaction_areas": selected_areas,
        "redaction_mode": payload.mode,
    }
    job.status = "pending"
    job.stage = "queued"
    job.progress = 0
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    db.commit()
    db.refresh(job)
    return job


@router.get("/jobs/{job_id}/pages/{page_number}")
def preview_page(
    job_id: int,
    page_number: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> Response:
    job = _owned_job(db, job_id, current_session.user_id)
    if job.source_content_type != "application/pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Preview is available only for PDF")
    try:
        data = render_pdf_page(Path(job.source_path), page_number)
    except DocumentToolError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


@router.get("/jobs/{job_id}/download")
def download_result(
    job_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> FileResponse:
    job = _owned_job(db, job_id, current_session.user_id)
    path = Path(job.result_path or "")
    if job.status != "completed" or not path.is_file():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Result is not ready")
    return FileResponse(path, media_type=job.result_content_type, filename=job.result_filename)


def _owned_job(db: Session, job_id: int, user_id: int) -> ToolJob:
    job = db.scalar(select(ToolJob).where(ToolJob.id == job_id, ToolJob.user_id == user_id))
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool job was not found")
    return job


def _pdf_document(db: Session, document_id: int, user_id: int):
    document = get_document_or_404(db, document_id, user_id)
    if document.content_type != "application/pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a PDF document")
    return document


def _create_job(db: Session, *, user_id: int, source_document_id: int | None, kind: str, filename: str, content_type: str, path: str, options: dict) -> ToolJob:
    job = ToolJob(
        user_id=user_id,
        source_document_id=source_document_id,
        kind=kind,
        source_filename=filename,
        source_content_type=content_type,
        source_path=path,
        options=options,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
