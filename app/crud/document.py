from collections.abc import Iterable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk


class DocumentChunkPayload:
    page_number: int | None
    chunk_index: int
    text: str
    extraction_method: str
    detected_language: str | None
    word_count: int
    char_count: int


def get_document(db: Session, document_id: int, user_id: int) -> Document | None:
    return db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.user_id == user_id,
        )
    )


def get_documents(db: Session, user_id: int) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.user_id == user_id)
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


def get_user_storage_bytes(db: Session, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(Document.size_bytes), 0)).where(
                Document.user_id == user_id
            )
        )
        or 0
    )


def create_document(
    db: Session,
    *,
    user_id: int,
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
        user_id=user_id,
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
    extraction_quality: str = "unknown",
    extraction_quality_meta: dict | None = None,
    detected_language: str | None = None,
    language_distribution: dict[str, float] | None = None,
    word_count: int = 0,
    char_count: int = 0,
    error_message: str | None = None,
    chunks: Iterable[DocumentChunkPayload] | None = None,
) -> Document:
    if extracted_text is not None:
        db_document.extracted_text = extracted_text
    db_document.extraction_quality = extraction_quality
    db_document.extraction_quality_meta = extraction_quality_meta or {}
    db_document.status = status
    db_document.detected_language = detected_language
    if language_distribution is not None:
        db_document.language_distribution = language_distribution
    db_document.word_count = word_count
    db_document.char_count = char_count
    db_document.error_message = error_message
    db_document.ai_summary = ""
    db_document.ai_model = None
    db_document.ai_error = None
    db_document.content_review = ""
    db_document.content_review_model = None
    db_document.content_review_error = None
    db_document.content_review_mode = None
    db_document.content_review_meta = {}

    if chunks is not None:
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == db_document.id))
        db.add_all(
            DocumentChunk(
                document_id=db_document.id,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                text=chunk.text,
                extraction_method=chunk.extraction_method,
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


def update_document_content_review(
    db: Session,
    db_document: Document,
    *,
    content_review: str,
    content_review_model: str | None,
    content_review_error: str | None,
    content_review_mode: str | None,
    content_review_meta: dict | None = None,
) -> Document:
    db_document.content_review = content_review
    db_document.content_review_model = content_review_model
    db_document.content_review_error = content_review_error
    db_document.content_review_mode = content_review_mode
    if content_review_meta is not None:
        db_document.content_review_meta = content_review_meta
    db.commit()
    db.refresh(db_document)
    return db_document


def update_document_layout_review(
    db: Session,
    db_document: Document,
    *,
    layout_review: str,
    layout_review_model: str | None,
    layout_review_error: str | None,
    layout_review_meta: dict | None = None,
) -> Document:
    db_document.layout_review = layout_review
    db_document.layout_review_model = layout_review_model
    db_document.layout_review_error = layout_review_error
    if layout_review_meta is not None:
        db_document.layout_review_meta = layout_review_meta
    db.commit()
    db.refresh(db_document)
    return db_document


def delete_document(db: Session, db_document: Document) -> None:
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == db_document.id))
    db.delete(db_document)
    db.commit()
