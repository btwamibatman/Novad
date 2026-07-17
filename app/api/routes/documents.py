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
from app.schemas.document import DocumentRead, DocumentReviewRequest
from app.services.file_storage import remove_stored_file, resolve_stored_path, save_upload
from app.services.rate_limit import enforce_rate_limit
from app.services import ai_content_review, ai_layout_review, ai_summary
from app.services.document_chunks import (
    build_document_chunks,
    format_chunks_for_context,
    language_distribution,
    primary_language,
    select_relevant_chunks,
)
from app.services.text_analysis import (
    analyze_text,
    assess_extraction_quality,
    extract_text_pages,
    join_page_text,
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


@router.post("/{document_id}/analyze", response_model=DocumentRead)
def analyze_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> Document:
    db_document = get_document_or_404(db, document_id, current_session.user_id)
    try:
        extracted_pages = extract_text_pages(db_document)
        extracted_text = join_page_text(extracted_pages).strip()
        _, word_count, char_count = analyze_text(extracted_text)
        chunks = build_document_chunks(extracted_pages)
        distribution = language_distribution(chunks)
        detected_language = primary_language(distribution)
        extraction_quality = assess_extraction_quality(extracted_pages)
    except Exception as error:
        return document_crud.update_document_analysis(
            db,
            db_document,
            status="failed",
            extracted_text="",
            extraction_quality="unknown",
            extraction_quality_meta={},
            language_distribution={},
            error_message=str(error),
            chunks=[],
        )

    return document_crud.update_document_analysis(
        db,
        db_document,
        status="processed",
        extracted_text=extracted_text,
        extraction_quality=extraction_quality.quality,
        extraction_quality_meta=extraction_quality.meta,
        detected_language=detected_language,
        language_distribution=distribution,
        word_count=word_count,
        char_count=char_count,
        error_message=None,
        chunks=chunks,
    )


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
    chunk_texts = [chunk.text for chunk in chunks] or [db_document.extracted_text]
    try:
        summary, model_name = await run_in_threadpool(
            ai_summary.summarize_chunks,
            chunk_texts,
            db_document.extraction_quality,
        )
    except ai_summary.AISummaryNotConfigured as error:
        document_crud.update_document_summary(
            db,
            db_document,
            ai_summary="",
            ai_model=None,
            ai_error=str(error),
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
        )
    ]
    try:
        result = await run_in_threadpool(
            ai_content_review.review_document_content,
            review_chunks,
            payload.mode,
        )
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
        content_review=result.text,
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
        },
    )


@router.post("/{document_id}/layout-review", response_model=DocumentRead)
async def review_document_layout(
    document_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> Document:
    await enforce_rate_limit(f"user:{current_session.user_id}", "layout-review", limit=5)
    db_document = get_document_or_404(db, document_id, current_session.user_id)
    if db_document.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Layout review is available only for PDF documents",
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
    selected_context = format_chunks_for_context(relevant_chunks) or db_document.extracted_text
    history = [message.model_dump() for message in payload.history[-12:]]
    try:
        answer, model_name, truncated_context = await run_in_threadpool(
            ai_summary.answer_document_question,
            selected_context,
            payload.question,
            history,
            db_document.extraction_quality,
        )
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
    document_crud.delete_document(db, db_document)
    remove_stored_file(stored_path)
    return None
