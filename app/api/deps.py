from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.crud import document as document_crud
from app.crud import session as session_crud
from app.core.config import settings
from app.core.database import get_db
from app.models.document import Document
from app.models.session import UserSession
from app.models.user import User


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path="/",
    )


def delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.is_production,
        httponly=True,
        samesite="lax",
    )


def get_current_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> UserSession:
    response.headers["Cache-Control"] = "no-store"
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    db_session = session_crud.get_session_by_token(db, token)
    if db_session is None or session_crud.is_expired(db_session):
        delete_session_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    db_user = db.get(User, db_session.user_id)
    if db_user is None or not db_user.is_active:
        session_crud.delete_session(db, db_session)
        delete_session_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    db_session = session_crud.touch_session(db, db_session)
    set_session_cookie(response, token)
    return db_session


def get_document_or_404(db: Session, document_id: int, user_id: int) -> Document:
    db_document = document_crud.get_document(db, document_id, user_id)
    if db_document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with id {document_id} was not found",
        )
    return db_document
