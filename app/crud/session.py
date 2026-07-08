from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.models.document import Document
from app.models.session import UserSession
from app.models._utils import utc_now
from app.services.file_storage import remove_stored_file


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def new_expires_at() -> datetime:
    return utc_now() + timedelta(minutes=settings.session_ttl_minutes)


def create_session(db: DbSession) -> UserSession:
    db_session = UserSession(expires_at=new_expires_at(), last_seen_at=utc_now())
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session


def get_session(db: DbSession, session_id: str) -> UserSession | None:
    return db.get(UserSession, session_id)


def is_expired(db_session: UserSession) -> bool:
    return _as_aware(db_session.expires_at) <= utc_now()


def touch_session(db: DbSession, db_session: UserSession) -> UserSession:
    db_session.last_seen_at = utc_now()
    db_session.expires_at = new_expires_at()
    db.commit()
    db.refresh(db_session)
    return db_session


def cleanup_expired_sessions(db: DbSession) -> int:
    expired_ids = list(
        db.scalars(select(UserSession.id).where(UserSession.expires_at <= utc_now())).all()
    )
    if not expired_ids:
        return 0

    stored_paths = list(
        db.scalars(select(Document.stored_path).where(Document.session_id.in_(expired_ids))).all()
    )
    for stored_path in stored_paths:
        remove_stored_file(stored_path)

    db.execute(delete(Document).where(Document.session_id.in_(expired_ids)))
    db.execute(delete(UserSession).where(UserSession.id.in_(expired_ids)))
    db.commit()
    return len(expired_ids)
