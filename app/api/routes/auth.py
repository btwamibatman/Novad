from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import delete_session_cookie, get_current_session, set_session_cookie
from app.core.config import settings
from app.core.database import get_db
from app.crud import session as session_crud
from app.crud import user as user_crud
from app.models.session import UserSession
from app.models.user import User
from app.schemas.auth import AuthSessionRead, AuthUserRead, LoginRequest
from app.services.password_hashing import verify_password_or_dummy
from app.services.rate_limit import enforce_rate_limit

router = APIRouter()


def auth_session_read(db_session: UserSession, db_user: User) -> AuthSessionRead:
    return AuthSessionRead(
        session_id=db_session.id,
        expires_at=db_session.expires_at,
        user=AuthUserRead(id=db_user.id, username=db_user.username),
    )


@router.post("/login", response_model=AuthSessionRead)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthSessionRead:
    client_host = request.client.host if request.client else "unknown"
    await enforce_rate_limit(f"login:{client_host}", "auth", limit=5)

    try:
        db_user = user_crud.get_user_by_username(db, payload.username)
    except ValueError:
        db_user = None
    password_valid = verify_password_or_dummy(
        payload.password,
        db_user.password_hash if db_user else None,
    )
    if db_user is None or not db_user.is_active or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    db_session, token = session_crud.create_session(db, db_user.id)
    set_session_cookie(response, token)
    response.headers["Cache-Control"] = "no-store"
    return auth_session_read(db_session, db_user)


@router.get("/me", response_model=AuthSessionRead)
def read_current_auth_session(
    response: Response,
    current_session: UserSession = Depends(get_current_session),
    db: Session = Depends(get_db),
) -> AuthSessionRead:
    db_user = db.get(User, current_session.user_id)
    if db_user is None or not db_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    response.headers["Cache-Control"] = "no-store"
    return auth_session_read(current_session, db_user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> None:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        db_session = session_crud.get_session_by_token(db, token)
        if db_session is not None:
            session_crud.delete_session(db, db_session)
    delete_session_cookie(response)
    response.headers["Cache-Control"] = "no-store"
