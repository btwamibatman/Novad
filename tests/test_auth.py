from argparse import Namespace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import create_user as create_user_cli
from app import claim_legacy_documents as claim_legacy_cli
from app.core.config import settings
from app.core.database import get_db
from app.crud.user import UserAlreadyExistsError, create_user, get_user_by_username
from app.crud import session as session_crud
from app.main import app
from app.models.document import Document
from app.models._utils import utc_now
from app.models.session import UserSession
from app.services.password_hashing import hash_password, verify_password
from tests.conftest import TestingSessionLocal, add_user, login_test_client, override_get_db


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


def test_protected_api_requires_authentication(anonymous_client):
    response = anonymous_client.get("/api/documents")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_login_sets_opaque_http_only_cookie(anonymous_client):
    add_user("admin", "strong password")

    response = anonymous_client.post(
        "/api/auth/login",
        json={"username": "ADMIN", "password": "strong password"},
    )

    assert response.status_code == 200
    assert response.json()["user"] == {"id": 1, "username": "admin"}
    assert response.json()["session_id"]
    set_cookie = response.headers["set-cookie"]
    assert "document_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Secure" not in set_cookie

    raw_token = response.cookies["document_session"]
    db = TestingSessionLocal()
    try:
        db_session = db.scalar(select(UserSession))
        assert db_session is not None
        assert db_session.token_hash != raw_token
        assert len(db_session.token_hash) == 64
    finally:
        db.close()


def test_login_uses_same_error_for_unknown_user_and_wrong_password(anonymous_client):
    add_user("admin", "correct password")

    unknown = anonymous_client.post(
        "/api/auth/login",
        json={"username": "unknown", "password": "wrong password"},
    )
    wrong_password = anonymous_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong password"},
    )

    assert unknown.status_code == 401
    assert wrong_password.status_code == 401
    assert unknown.json() == wrong_password.json() == {
        "detail": "Invalid username or password"
    }


def test_logout_revokes_server_session(client):
    assert client.get("/api/auth/me").status_code == 200

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    db = TestingSessionLocal()
    try:
        assert db.scalar(select(UserSession)) is None
    finally:
        db.close()


def test_production_login_cookie_is_secure(anonymous_client, monkeypatch):
    add_user("admin", "strong password")
    monkeypatch.setattr(settings, "environment", "production")

    response = anonymous_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "strong password"},
    )

    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]


def test_login_rate_limit_blocks_repeated_attempts(anonymous_client):
    for _ in range(5):
        response = anonymous_client.post(
            "/api/auth/login",
            json={"username": "unknown", "password": "wrong password"},
        )
        assert response.status_code == 401

    response = anonymous_client.post(
        "/api/auth/login",
        json={"username": "unknown", "password": "wrong password"},
    )

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1


def test_same_user_can_access_documents_from_a_new_login(client, pdf_document_id):
    app.dependency_overrides[get_db] = override_get_db
    second_browser = TestClient(app)
    login_test_client(second_browser, "test-user")

    response = second_browser.get(f"/api/documents/{pdf_document_id}")

    assert response.status_code == 200
    assert response.json()["id"] == pdf_document_id


def test_expired_login_session_does_not_delete_user_document(client, pdf_document_id):
    db = TestingSessionLocal()
    try:
        db_session = db.scalar(select(UserSession))
        db_session.expires_at = utc_now() - timedelta(seconds=1)
        db.commit()

        assert session_crud.cleanup_expired_sessions(db) == 1

        db_document = db.get(Document, pdf_document_id)
        assert db_document is not None
        assert db_document.user_id is not None
        assert db_document.session_id is None
    finally:
        db.close()


def test_claim_legacy_documents_assigns_owner(monkeypatch):
    db = TestingSessionLocal()
    try:
        db_user = create_user(
            db,
            username="admin",
            password_hash=hash_password("server password"),
        )
        legacy_session = UserSession()
        db.add(legacy_session)
        db.flush()
        db_document = Document(
            session_id=legacy_session.id,
            user_id=None,
            filename="legacy.pdf",
            stored_filename="legacy.pdf",
            stored_path="legacy.pdf",
            content_type="application/pdf",
            size_bytes=10,
        )
        db.add(db_document)
        db.commit()
        document_id = db_document.id
    finally:
        db.close()

    monkeypatch.setattr(claim_legacy_cli, "init_db", lambda: None)
    monkeypatch.setattr(claim_legacy_cli, "create_session", TestingSessionLocal)

    assert claim_legacy_cli.claim_legacy_documents("admin") == 1

    db = TestingSessionLocal()
    try:
        claimed_document = db.get(Document, document_id)
        assert claimed_document.user_id == db_user.id
        assert claimed_document.session_id is None
    finally:
        db.close()
