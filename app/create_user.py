from __future__ import annotations

import argparse
from getpass import getpass
import sys

from app.core.database import create_session, init_db
from app.crud.user import UserAlreadyExistsError, create_user, normalize_username
from app.services.password_hashing import hash_password


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Document Console user")
    parser.add_argument("username", help="Username used to sign in")
    return parser.parse_args()


def prompt_password() -> str:
    password = getpass("Password: ")
    confirmation = getpass("Confirm password: ")
    if not password:
        raise ValueError("Password is required")
    if password != confirmation:
        raise ValueError("Passwords do not match")
    return password


def main() -> int:
    args = parse_args()
    try:
        username = normalize_username(args.username)
        password = prompt_password()
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    init_db()
    db = create_session()
    try:
        db_user = create_user(
            db,
            username=username,
            password_hash=hash_password(password),
        )
    except UserAlreadyExistsError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"Created user '{db_user.username}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
