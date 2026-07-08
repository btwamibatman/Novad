from fastapi import APIRouter, Depends

from app.api.deps import get_current_session
from app.models.session import UserSession
from app.schemas.session import SessionRead

router = APIRouter()


@router.get("", response_model=SessionRead)
def read_session(current_session: UserSession = Depends(get_current_session)) -> SessionRead:
    return SessionRead(
        session_id=current_session.id,
        expires_at=current_session.expires_at,
    )
