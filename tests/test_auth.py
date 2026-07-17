from argparse import Namespace

import pytest

from app import create_user as create_user_cli
from app.crud.user import UserAlreadyExistsError, create_user, get_user_by_username
from app.services.password_hashing import hash_password, verify_password
from tests.conftest import TestingSessionLocal


def test_argon2_hash_uses_unique_salt_and_verifies_password():
    password = "correct horse battery staple"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash.startswith("$argon2id$")
    assert second_hash.startswith("$argon2id$")
    assert first_hash != second_hash
    assert verify_password(password, first_hash) is True
    assert verify_password("wrong password", first_hash) is False


def test_create_user_stores_normalized_username_and_password_hash():
    db = TestingSessionLocal()
    encoded_hash = hash_password("secret password")
    try:
        db_user = create_user(db, username="  Admin  ", password_hash=encoded_hash)

        assert db_user.username == "admin"
        assert db_user.password_hash == encoded_hash
        assert db_user.password_hash != "secret password"
        assert db_user.is_active is True
        assert get_user_by_username(db, "ADMIN").id == db_user.id
    finally:
        db.close()


def test_create_user_rejects_duplicate_normalized_username():
    db = TestingSessionLocal()
    try:
        create_user(db, username="admin", password_hash=hash_password("first password"))

        with pytest.raises(UserAlreadyExistsError, match="already exists"):
            create_user(db, username=" ADMIN ", password_hash=hash_password("second password"))
    finally:
        db.close()


def test_create_user_cli_hashes_password_and_creates_user(monkeypatch, capsys):
    monkeypatch.setattr(
        create_user_cli,
        "parse_args",
        lambda: Namespace(username="Admin"),
    )
    monkeypatch.setattr(create_user_cli, "prompt_password", lambda: "server password")
    monkeypatch.setattr(create_user_cli, "init_db", lambda: None)
    monkeypatch.setattr(create_user_cli, "create_session", TestingSessionLocal)

    assert create_user_cli.main() == 0

    output = capsys.readouterr()
    assert output.out.strip() == "Created user 'admin'."
    assert "server password" not in output.out

    db = TestingSessionLocal()
    try:
        db_user = get_user_by_username(db, "admin")
        assert db_user is not None
        assert db_user.password_hash != "server password"
        assert verify_password("server password", db_user.password_hash) is True
    finally:
        db.close()
