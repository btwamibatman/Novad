from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.api.deps import get_current_session, get_document_or_404
from app.core.config import settings
from app.core.database import get_db
from app.crud import document as document_crud
from app.models.document import Document
from app.models.session import UserSession
from app.schemas.ai_chat import AIChatRequest, AIChatResponse
from app.schemas.document import DocumentRead
from app.services.file_storage import remove_stored_file, resolve_stored_path, save_upload
from app.services.rate_limit import enforce_rate_limit
from app.services import ai_summary
from app.services.text_analysis import analyze_text, extract_text

router = APIRouter()


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> Document:
    await enforce_rate_limit(current_session.id, "upload", limit=10)
    filename, stored_filename, stored_path, content_type, size_bytes = await save_upload(file)
    used_bytes = document_crud.get_session_storage_bytes(db, current_session.id)
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
    return document_crud.get_documents(db, current_session.id)


@router.get("/{document_id}", response_model=DocumentRead)
def read_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> Document:
    return get_document_or_404(db, document_id, current_session.id)


@router.post("/{document_id}/analyze", response_model=DocumentRead)
def analyze_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> Document:
    db_document = get_document_or_404(db, document_id, current_session.id)
    try:
        extracted_text = extract_text(db_document)
        detected_language, word_count, char_count = analyze_text(extracted_text)
    except Exception as error:
        return document_crud.update_document_analysis(
            db,
            db_document,
            status="failed",
            error_message=str(error),
        )

    return document_crud.update_document_analysis(
        db,
        db_document,
        status="processed",
        extracted_text=extracted_text.strip(),
        detected_language=detected_language,
        word_count=word_count,
        char_count=char_count,
        error_message=None,
    )


@router.post("/{document_id}/summarize", response_model=DocumentRead)
async def summarize_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> Document:
    await enforce_rate_limit(current_session.id, "summarize", limit=5)
    db_document = get_document_or_404(db, document_id, current_session.id)
    if db_document.status != "processed" or not db_document.extracted_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document must be analyzed first",
        )

    try:
        summary, model_name = await run_in_threadpool(
            ai_summary.summarize_text,
            db_document.extracted_text,
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


@router.post("/{document_id}/ask", response_model=AIChatResponse)
async def ask_document_question(
    document_id: int,
    payload: AIChatRequest,
    db: Session = Depends(get_db),
    current_session: UserSession = Depends(get_current_session),
) -> AIChatResponse:
    await enforce_rate_limit(current_session.id, "ask", limit=10)
    db_document = get_document_or_404(db, document_id, current_session.id)
    if db_document.status != "processed" or not db_document.extracted_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document must be analyzed first",
        )

    history = [message.model_dump() for message in payload.history[-12:]]
    try:
        answer, model_name, truncated_context = await run_in_threadpool(
            ai_summary.answer_document_question,
            db_document.extracted_text,
            payload.question,
            history,
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
    db_document = get_document_or_404(db, document_id, current_session.id)
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
    db_document = get_document_or_404(db, document_id, current_session.id)
    stored_path = db_document.stored_path
    document_crud.delete_document(db, db_document)
    remove_stored_file(stored_path)
    return None
