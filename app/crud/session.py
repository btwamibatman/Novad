from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.session import UserSession
from app.models._utils import utc_now
from app.services.file_storage import remove_stored_file


def _as_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def new_expires_at() -> datetime:
    return utc_now() + timedelta(minutes=settings.session_ttl_minutes)


def hash_session_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_session(db: DbSession, user_id: int) -> tuple[UserSession, str]:
    token = token_urlsafe(32)
    db_session = UserSession(
        user_id=user_id,
        token_hash=hash_session_token(token),
        expires_at=new_expires_at(),
        last_seen_at=utc_now(),
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    return db_session, token


def get_session_by_token(db: DbSession, token: str) -> UserSession | None:
    return db.scalar(
        select(UserSession).where(UserSession.token_hash == hash_session_token(token))
    )


def is_expired(db_session: UserSession) -> bool:
    return _as_aware(db_session.expires_at) <= utc_now()


def touch_session(db: DbSession, db_session: UserSession) -> UserSession:
    db_session.last_seen_at = utc_now()
    db_session.expires_at = new_expires_at()
    db.commit()
    db.refresh(db_session)
    return db_session


def delete_session(db: DbSession, db_session: UserSession) -> None:
    db.execute(
        update(Document)
        .where(Document.session_id == db_session.id, Document.user_id.is_not(None))
        .values(session_id=None)
    )
    db.delete(db_session)
    db.commit()


def cleanup_expired_sessions(db: DbSession) -> int:
    expired_ids = list(
        db.scalars(select(UserSession.id).where(UserSession.expires_at <= utc_now())).all()
    )
    if not expired_ids:
        return 0

    legacy_filter = (
        Document.session_id.in_(expired_ids),
        Document.user_id.is_(None),
    )
    stored_paths = list(db.scalars(select(Document.stored_path).where(*legacy_filter)).all())
    for stored_path in stored_paths:
        remove_stored_file(stored_path)

    document_ids = list(
        db.scalars(select(Document.id).where(*legacy_filter)).all()
    )
    if document_ids:
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id.in_(document_ids)))
    db.execute(delete(Document).where(*legacy_filter))
    db.execute(
        update(Document)
        .where(Document.session_id.in_(expired_ids), Document.user_id.is_not(None))
        .values(session_id=None)
    )
    db.execute(delete(UserSession).where(UserSession.id.in_(expired_ids)))
    db.commit()
    return len(expired_ids)
