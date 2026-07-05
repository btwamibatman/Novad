from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.crud import document as document_crud
from app.models.document import Document


def get_document_or_404(db: Session, document_id: int) -> Document:
    db_document = document_crud.get_document(db, document_id)
    if db_document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found",
        )
    return db_document
