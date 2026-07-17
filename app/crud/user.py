from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User


class UserAlreadyExistsError(ValueError):
    pass


def normalize_username(username: str) -> str:
    normalized = username.strip().casefold()
    if not normalized:
        raise ValueError("Username is required")
    if len(normalized) > 100:
        raise ValueError("Username must be at most 100 characters")
    return normalized


def get_user_by_username(db: Session, username: str) -> User | None:
    normalized = normalize_username(username)
    return db.scalar(select(User).where(User.username == normalized))


def create_user(db: Session, *, username: str, password_hash: str) -> User:
    normalized = normalize_username(username)
    db_user = User(username=normalized, password_hash=password_hash)
    db.add(db_user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise UserAlreadyExistsError(
            f"User '{normalized}' already exists"
        ) from error
    db.refresh(db_user)
    return db_user
