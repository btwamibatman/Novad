from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.document import Document


def get_document(db: Session, document_id: int, session_id: str) -> Document | None:
    return db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.session_id == session_id,
        )
    )


def get_documents(db: Session, session_id: str) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.session_id == session_id)
            .order_by(Document.created_at.desc())
        ).all()
    )


def get_session_storage_bytes(db: Session, session_id: str) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Document.size_bytes), 0)).where(
                Document.session_id == session_id
            )
        )
        or 0
    )


def create_document(
    db: Session,
    *,
    session_id: str,
    filename: str,
    stored_filename: str,
    stored_path: str,
    content_type: str,
    size_bytes: int,
) -> Document:
    db_document = Document(
        filename=filename,
        stored_filename=stored_filename,
        stored_path=stored_path,
        content_type=content_type,
        size_bytes=size_bytes,
        session_id=session_id,
        status="uploaded",
    )
    db.add(db_document)
    db.commit()
    db.refresh(db_document)
    return db_document


def update_document_analysis(
    db: Session,
    db_document: Document,
    *,
    status: str,
    extracted_text: str | None = None,
    detected_language: str | None = None,
    word_count: int = 0,
    char_count: int = 0,
    error_message: str | None = None,
) -> Document:
    if extracted_text is not None:
        db_document.extracted_text = extracted_text
    db_document.status = status
    db_document.detected_language = detected_language
    db_document.word_count = word_count
    db_document.char_count = char_count
    db_document.error_message = error_message
    db.commit()
    db.refresh(db_document)
    return db_document


def update_document_summary(
    db: Session,
    db_document: Document,
    *,
    ai_summary: str,
    ai_model: str | None,
    ai_error: str | None = None,
) -> Document:
    db_document.ai_summary = ai_summary
    db_document.ai_model = ai_model
    db_document.ai_error = ai_error
    db.commit()
    db.refresh(db_document)
    return db_document


def delete_document(db: Session, db_document: Document) -> None:
    db.delete(db_document)
    db.commit()
