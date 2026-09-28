from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.core.config import Settings, settings
from app.core.database import Base, get_db
from app.crud.user import create_user
from app.main import app
from app.services.analysis_jobs import run_next_analysis_job
from app.services.password_hashing import hash_password
from app.services.rate_limit import _buckets
from tests.helpers.pdf import make_pdf_with_text

TEST_DATABASE_URL = "sqlite://"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def reset_database(tmp_path, monkeypatch) -> Generator[None, None, None]:
    # Tests use application defaults, not the developer's environment or .env.
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    defaults = Settings(_env_file=None)
    for name in Settings.model_fields:
        monkeypatch.setattr(settings, name, getattr(defaults, name))
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "pii_masking_enabled", False)
    _buckets.clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        Base.metadata.drop_all(bind=engine)
        _buckets.clear()
    # pytest owns tmp_path; never delete a path read from mutable settings.


def add_user(username: str, password: str = "test password") -> None:
    db = TestingSessionLocal()
    try:
        create_user(db, username=username, password_hash=hash_password(password))
    finally:
        db.close()


def login_test_client(test_client: TestClient, username: str, password: str = "test password") -> None:
    response = test_client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200


@pytest.fixture()
def client(monkeypatch) -> Generator[TestClient, None, None]:
    monkeypatch.setitem(app.dependency_overrides, get_db, override_get_db)
    test_client = TestClient(app)
    try:
        add_user("test-user")
        login_test_client(test_client, "test-user")
        yield test_client
    finally:
        test_client.close()


@pytest.fixture()
def other_client(monkeypatch) -> Generator[TestClient, None, None]:
    monkeypatch.setitem(app.dependency_overrides, get_db, override_get_db)
    test_client = TestClient(app)
    try:
        add_user("other-user")
        login_test_client(test_client, "other-user")
        yield test_client
    finally:
        test_client.close()


@pytest.fixture()
def anonymous_client(monkeypatch) -> Generator[TestClient, None, None]:
    monkeypatch.setitem(app.dependency_overrides, get_db, override_get_db)
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()


@pytest.fixture()
def pdf_document_id(client: TestClient) -> int:
    response = client.post(
        "/api/documents/upload",
        files={
            "file": (
                "sample.pdf",
                make_pdf_with_text(
                    "This document contains enough English text for language detection."
                ),
                "application/pdf",
            )
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture()
def analysis_runner():
    def run_all() -> None:
        while run_next_analysis_job(TestingSessionLocal):
            pass

    return run_all
