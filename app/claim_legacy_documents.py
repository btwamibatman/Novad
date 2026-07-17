from __future__ import annotations

import argparse
import sys

from sqlalchemy import update

from app.core.database import create_session, init_db
from app.crud.user import get_user_by_username
from app.models.document import Document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assign legacy anonymous documents to an existing user"
    )
    parser.add_argument("username", help="User who will own the legacy documents")
    return parser.parse_args()


def claim_legacy_documents(username: str) -> int:
    init_db()
    db = create_session()
    try:
        db_user = get_user_by_username(db, username)
        if db_user is None:
            raise ValueError(f"User '{username.strip()}' was not found")
        result = db.execute(
            update(Document)
            .where(Document.user_id.is_(None))
            .values(user_id=db_user.id, session_id=None)
        )
        db.commit()
        return int(result.rowcount or 0)
    finally:
        db.close()


def main() -> int:
    args = parse_args()
    try:
        claimed_count = claim_legacy_documents(args.username)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Assigned {claimed_count} legacy document(s) to '{args.username.strip().casefold()}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
