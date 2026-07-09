from collections.abc import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk


class DocumentChunkPayload:
    page_number: int | None
    chunk_index: int
    text: str
    detected_language: str | None
    word_count: int
    char_count: int


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


def get_document_chunks(db: Session, document_id: int) -> list[DocumentChunk]:
    return list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
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
    language_distribution: dict[str, float] | None = None,
    word_count: int = 0,
    char_count: int = 0,
    error_message: str | None = None,
    chunks: Iterable[DocumentChunkPayload] | None = None,
) -> Document:
    if extracted_text is not None:
        db_document.extracted_text = extracted_text
    db_document.status = status
    db_document.detected_language = detected_language
    if language_distribution is not None:
        db_document.language_distribution = language_distribution
    db_document.word_count = word_count
    db_document.char_count = char_count
    db_document.error_message = error_message

    if chunks is not None:
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == db_document.id))
        db.add_all(
            DocumentChunk(
                document_id=db_document.id,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                detected_language=chunk.detected_language,
                word_count=chunk.word_count,
                char_count=chunk.char_count,
            )
            for chunk in chunks
        )

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
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == db_document.id))
    db.delete(db_document)
    db.commit()
