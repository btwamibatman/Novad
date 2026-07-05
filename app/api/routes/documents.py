from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_document_or_404
from app.core.database import get_db
from app.crud import document as document_crud
from app.models.document import Document
from app.schemas.document import DocumentRead
from app.services.file_storage import remove_stored_file, resolve_stored_path, save_upload
from app.services import ai_summary
from app.services.text_analysis import analyze_text, extract_text

router = APIRouter()


@router.post("/upload", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Document:
    filename, stored_filename, stored_path, content_type, size_bytes = await save_upload(file)
    try:
        return document_crud.create_document(
            db,
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
def read_documents(db: Session = Depends(get_db)) -> list[Document]:
    return document_crud.get_documents(db)


@router.get("/{document_id}", response_model=DocumentRead)
def read_document(document_id: int, db: Session = Depends(get_db)) -> Document:
    return get_document_or_404(db, document_id)


@router.post("/{document_id}/analyze", response_model=DocumentRead)
def analyze_document(document_id: int, db: Session = Depends(get_db)) -> Document:
    db_document = get_document_or_404(db, document_id)
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
def summarize_document(document_id: int, db: Session = Depends(get_db)) -> Document:
    db_document = get_document_or_404(db, document_id)
    if db_document.status != "processed" or not db_document.extracted_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document must be analyzed first",
        )

    try:
        summary, model_name = ai_summary.summarize_text(db_document.extracted_text)
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


@router.get("/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db)) -> FileResponse:
    db_document = get_document_or_404(db, document_id)
    return FileResponse(
        resolve_stored_path(db_document.stored_path),
        media_type=db_document.content_type,
        filename=db_document.filename,
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, db: Session = Depends(get_db)) -> None:
    db_document = get_document_or_404(db, document_id)
    stored_path = db_document.stored_path
    document_crud.delete_document(db, db_document)
    remove_stored_file(stored_path)
    return None
