from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import get_current_session, get_document_or_404
from app.core.config import settings
from app.core.database import get_db
from app.crud import document as document_crud
from app.models.document import Document
from app.models._utils import utc_now
from app.models.session import UserSession
from app.schemas.ai_chat import AIChatRequest, AIChatResponse
from app.schemas.document import (
    DocumentLayoutReviewRequest,
    DocumentRead,
    DocumentReviewRequest,
)
from app.services.ai import content_review as ai_content_review
from app.services.ai import summary as ai_summary
from app.services.file_storage import remove_stored_file, resolve_stored_path, save_upload
from app.services.rate_limit import enforce_rate_limit
from app.services.ai import layout_review as ai_layout_review
from app.services.ai.jobs import AIAnalysisJobError, AIAnalysisJobsActive
from app.services.ai.provider import AIProviderError, AIProviderNotConfigured
from app.services.analysis_jobs import enqueue_analysis
from app.services.pii_masking import (
    PIIMaskingError,
    PIIMaskingSession,
    PIIMaskingUnavailable,
)
from app.services.documents.chunks import (
    format_chunks_for_context,
    select_relevant_chunks,
)

router = APIRouter()


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> Document:
    await enforce_rate_limit(f"user:{current_session.user_id}", "upload", limit=10)
    filename, stored_filename, stored_path, content_type, size_bytes = await save_upload(file)
    used_bytes = document_crud.get_user_storage_bytes(db, current_session.user_id)
    if used_bytes + size_bytes > settings.session_storage_quota_bytes:
        remove_stored_file(stored_path)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "message": "Session storage quota exceeded",
                "used_bytes": used_bytes,
                "quota_bytes": settings.session_storage_quota_bytes,
                "remaining_bytes": max(settings.session_storage_quota_bytes - used_bytes, 0),
            },
        )
    try:
        return document_crud.create_document(
            db,
            user_id=current_session.user_id,
            session_id=current_session.id,
            filename=filename,
            stored_filename=stored_filename,
            stored_path=stored_path,
            content_type=content_type,
            size_bytes=size_bytes,
        )
    except Exception:
        remove_stored_file(stored_path)
        raise


@router.get("", response_model=list[DocumentRead])
def read_documents(
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> list[Document]:
    return document_crud.get_documents(db, current_session.user_id)


@router.get("/{document_id}", response_model=DocumentRead)
def read_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> Document:
    return get_document_or_404(db, document_id, current_session.user_id)


@router.post(
    "/{document_id}/analyze",
    response_model=DocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> Document:
    db_document = get_document_or_404(db, document_id, current_session.user_id)
    return enqueue_analysis(db, db_document)


@router.post("/{document_id}/summarize", response_model=DocumentRead)
async def summarize_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> Document:
    await enforce_rate_limit(f"user:{current_session.user_id}", "summarize", limit=5)
    db_document = get_document_or_404(db, document_id, current_session.user_id)
    if db_document.status != "processed" or not db_document.extracted_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document must be analyzed first",
        )

    chunks = document_crud.get_document_chunks(db, db_document.id)
    chunk_texts = (
        [format_chunks_for_context([chunk]) for chunk in chunks]
        or [
            "[document, extraction="
            f"unknown, quality={db_document.extraction_quality}, confidence=n/a, "
            "uncertain_regions=0]\n"
            f"{db_document.extracted_text}"
        ]
    )
    privacy = PIIMaskingSession()
    try:
        masked_chunk_texts = [privacy.mask(text) for text in chunk_texts]
        summary, model_name = await run_in_threadpool(
            ai_summary.summarize_chunks,
            masked_chunk_texts,
            db_document.extraction_quality,
        )
        summary = privacy.restore(summary)
    except PIIMaskingUnavailable as error:
        document_crud.update_document_summary(
            db,
            db_document,
            ai_summary="",
            ai_model=None,
            ai_error=str(error),
            ai_summary_meta={},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except PIIMaskingError as error:
        document_crud.update_document_summary(
            db,
            db_document,
            ai_summary="",
            ai_model=None,
            ai_error=str(error),
            ai_summary_meta={},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI summary privacy processing failed",
        ) from error
    except ai_summary.AISummaryNotConfigured as error:
        document_crud.update_document_summary(
            db,
            db_document,
            ai_summary="",
            ai_model=None,
            ai_error=str(error),
            ai_summary_meta={},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except ai_summary.AISummaryError as error:
        document_crud.update_document_summary(
            db,
            db_document,
            ai_summary="",
            ai_model=None,
            ai_error=str(error),
            ai_summary_meta={},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI summary generation failed",
        ) from error
    except Exception as error:
        document_crud.update_document_summary(
            db,
            db_document,
            ai_summary="",
            ai_model=None,
            ai_error=str(error),
            ai_summary_meta={},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI summary generation failed",
        ) from error

    return document_crud.update_document_summary(
        db,
        db_document,
        ai_summary=summary,
        ai_model=model_name,
        ai_error=None,
        ai_summary_meta={
            "provider": settings.ai_provider,
            "privacy": privacy.meta.as_dict(),
            "generated_at": utc_now().isoformat(),
        },
    )


@router.post("/{document_id}/content-review", response_model=DocumentRead)
async def review_document_content(
    document_id: int,
    payload: DocumentReviewRequest,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> Document:
    rate_limit = 5 if payload.mode == "quick" else 1
    await enforce_rate_limit(
        f"user:{current_session.user_id}",
        f"content-review-{payload.mode}",
        limit=rate_limit,
    )
    db_document = get_document_or_404(db, document_id, current_session.user_id)
    if db_document.status != "processed" or not db_document.extracted_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document must be analyzed first",
        )

    chunks = document_crud.get_document_chunks(db, db_document.id)
    review_chunks = chunks or [
        ai_content_review.ReviewChunkData(
            chunk_index=0,
            page_number=None,
            text=db_document.extracted_text,
            extraction_quality=db_document.extraction_quality,
        )
    ]
    privacy = PIIMaskingSession()
    try:
        masked_review_chunks = [
            ai_content_review.ReviewChunkData(
                chunk_index=chunk.chunk_index,
                page_number=chunk.page_number,
                text=privacy.mask(chunk.text),
                extraction_method=getattr(chunk, "extraction_method", "unknown"),
                extraction_quality=getattr(
                    chunk, "extraction_quality", "unknown"
                ),
                confidence=getattr(chunk, "confidence", None),
                uncertain_region_count=getattr(
                    chunk, "uncertain_region_count", 0
                ),
            )
            for chunk in review_chunks
        ]
        result = await run_in_threadpool(
            ai_content_review.review_document_content,
            masked_review_chunks,
            payload.mode,
        )
        review_text = privacy.restore(result.text)
    except PIIMaskingUnavailable as error:
        _store_content_review_error(db, db_document, payload.mode, error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except PIIMaskingError as error:
        _store_content_review_error(db, db_document, payload.mode, error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI content review privacy processing failed",
        ) from error
    except ai_content_review.ContentReviewNotConfigured as error:
        _store_content_review_error(db, db_document, payload.mode, error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except ai_content_review.ContentReviewTooLarge as error:
        _store_content_review_error(db, db_document, payload.mode, error)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(error),
        ) from error
    except ai_content_review.ContentReviewError as error:
        _store_content_review_error(db, db_document, payload.mode, error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI content review failed",
        ) from error
    except Exception as error:
        _store_content_review_error(db, db_document, payload.mode, error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI content review failed",
        ) from error

    return document_crud.update_document_content_review(
        db,
        db_document,
        content_review=review_text,
        content_review_model=result.model,
        content_review_error=None,
        content_review_mode=result.mode,
        content_review_meta={
            "mode": result.mode,
            "complete": result.complete,
            "batch_count": result.batch_count,
            "total_chars": db_document.char_count,
            "reviewed_chars": (
                db_document.char_count
                if result.complete
                else min(result.reviewed_chars, db_document.char_count)
            ),
            "provider": settings.ai_provider,
            "extraction_quality": db_document.extraction_quality,
            "requires_manual_review": db_document.extraction_quality_meta.get(
                "requires_manual_review", False
            ),
            "reviewed_at": utc_now().isoformat(),
            "privacy": privacy.meta.as_dict(),
        },
    )


@router.post("/{document_id}/layout-review", response_model=DocumentRead)
async def review_document_layout(
    document_id: int,
    payload: DocumentLayoutReviewRequest | None = None,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> Document:
    if payload is None or not payload.consent_to_external_image_processing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Explicit consent to external image processing is required",
        )
    await enforce_rate_limit(f"user:{current_session.user_id}", "layout-review", limit=5)
    db_document = get_document_or_404(db, document_id, current_session.user_id)
    if db_document.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Layout review is available only for PDF documents",
        )
    if (
        settings.ai_provider.strip().lower() == "gemini"
        and settings.gemini_service_tier == "unpaid"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Original PDF page images are blocked for unpaid Gemini. "
                "Create a verified protected copy and run protected layout review."
            ),
        )

    try:
        result = await run_in_threadpool(
            ai_layout_review.review_pdf_layout,
            resolve_stored_path(db_document.stored_path),
        )
    except ai_layout_review.LayoutReviewNotConfigured as error:
        _store_layout_review_error(db, db_document, error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except ai_layout_review.LayoutReviewInputError as error:
        _store_layout_review_error(db, db_document, error)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    except ai_layout_review.LayoutReviewError as error:
        _store_layout_review_error(db, db_document, error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI layout review failed",
        ) from error
    except Exception as error:
        _store_layout_review_error(db, db_document, error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI layout review failed",
        ) from error

    return document_crud.update_document_layout_review(
        db,
        db_document,
        layout_review=result.text,
        layout_review_model=result.model,
        layout_review_error=None,
        layout_review_meta={
            "complete": result.complete,
            "total_pages": result.total_pages,
            "reviewed_pages": result.reviewed_pages,
            "dpi": result.dpi,
            "requested_dpi": settings.layout_review_dpi,
            "adaptive_dpi": result.dpi < settings.layout_review_dpi,
            "provider": settings.ai_provider,
            "external_processing": settings.ai_provider.strip().lower() == "gemini",
            "external_image_processing_consent": True,
            "standard": ai_layout_review.RK_LAYOUT_STANDARD_REFERENCE,
            "standard_source": ai_layout_review.RK_LAYOUT_STANDARD_SOURCE,
            "reviewed_at": utc_now().isoformat(),
        },
    )


def _store_content_review_error(
    db: Session,
    db_document: Document,
    mode: str,
    error: Exception,
) -> None:
    document_crud.update_document_content_review(
        db,
        db_document,
        content_review="",
        content_review_model=None,
        content_review_error=str(error),
        content_review_mode=mode,
        content_review_meta={},
    )


def _store_layout_review_error(
    db: Session,
    db_document: Document,
    error: Exception,
) -> None:
    document_crud.update_document_layout_review(
        db,
        db_document,
        layout_review="",
        layout_review_model=None,
        layout_review_error=str(error),
        layout_review_meta={},
    )


@router.post("/{document_id}/ask", response_model=AIChatResponse)
async def ask_document_question(
    document_id: int,
    payload: AIChatRequest,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> AIChatResponse:
    await enforce_rate_limit(f"user:{current_session.user_id}", "ask", limit=10)
    db_document = get_document_or_404(db, document_id, current_session.user_id)
    if db_document.status != "processed" or not db_document.extracted_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document must be analyzed first",
        )

    chunks = document_crud.get_document_chunks(db, db_document.id)
    relevant_chunks = select_relevant_chunks(chunks, payload.question)
    selected_context = format_chunks_for_context(relevant_chunks) or (
        "[document, extraction=unknown, "
        f"quality={db_document.extraction_quality}, confidence=n/a, "
        "uncertain_regions=0]\n"
        f"{db_document.extracted_text}"
    )
    history = [message.model_dump() for message in payload.history[-12:]]
    privacy = PIIMaskingSession()
    try:
        masked_context = privacy.mask(selected_context)
        masked_question = privacy.mask(payload.question)
        masked_history = [
            {**message, "content": privacy.mask(message["content"])}
            for message in history
        ]
        answer, model_name, truncated_context = await run_in_threadpool(
            ai_summary.answer_document_question,
            masked_context,
            masked_question,
            masked_history,
            db_document.extraction_quality,
        )
        answer = privacy.restore(answer)
    except PIIMaskingUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except PIIMaskingError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI question privacy processing failed",
        ) from error
    except ai_summary.AISummaryNotConfigured as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except ai_summary.AISummaryError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI question answering failed",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI question answering failed",
        ) from error

    return AIChatResponse(
        answer=answer,
        model=model_name,
        truncated_context=truncated_context,
        privacy_applied=privacy.meta.applied,
        masked_entity_count=privacy.meta.entity_count,
    )


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> FileResponse:
    db_document = get_document_or_404(db, document_id, current_session.user_id)
    return FileResponse(
        resolve_stored_path(db_document.stored_path),
        media_type=db_document.content_type,
        filename=db_document.filename,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> None:
    db_document = get_document_or_404(db, document_id, current_session.user_id)
    stored_path = db_document.stored_path
    try:
        document_crud.delete_document(db, db_document)
    except AIAnalysisJobsActive as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except (AIProviderNotConfigured, AIAnalysisJobError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="External AI copy cleanup is temporarily unavailable",
        ) from error
    except AIProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="External AI copy could not be deleted",
        ) from error
    remove_stored_file(stored_path)
    return None
