from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.crud import document as document_crud
from app.crud import session as session_crud
from app.core.config import settings
from app.core.database import get_db
from app.models.document import Document
from app.models.session import UserSession


def set_session_cookie(response: Response, db_session: UserSession) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        db_session.id,
        max_age=settings.session_ttl_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.environment != "development",
    )


def get_current_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> UserSession:
    session_crud.cleanup_expired_sessions(db)
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        db_session = session_crud.create_session(db)
        set_session_cookie(response, db_session)
        return db_session

    db_session = session_crud.get_session(db, session_id)
    if db_session is None or session_crud.is_expired(db_session):
        response.delete_cookie(settings.session_cookie_name)
        raise HTTPException(
            status_code=419,
            detail="Session expired, upload files again",
        )

    db_session = session_crud.touch_session(db, db_session)
    set_session_cookie(response, db_session)
    return db_session


def get_document_or_404(db: Session, document_id: int, session_id: str) -> Document:
    db_document = document_crud.get_document(db, document_id, session_id)
    if db_document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found",
        )
    return db_document
