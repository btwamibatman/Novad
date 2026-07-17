from collections.abc import Generator
import shutil

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.core.config import settings
from app.core.database import Base, get_db
from app.crud.user import create_user
from app.main import app
from app.services.password_hashing import hash_password
from app.services.rate_limit import _buckets
from tests.pdf_helpers import make_pdf_with_text

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
def reset_database(tmp_path) -> Generator[None, None, None]:
    original_environment = settings.environment
    settings.storage_dir = str(tmp_path / "uploads")
    settings.environment = "development"
    _buckets.clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    _buckets.clear()
    settings.environment = original_environment
    shutil.rmtree(settings.storage_dir, ignore_errors=True)


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
def client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    add_user("test-user")
    login_test_client(test_client, "test-user")
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def other_client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    add_user("other-user")
    login_test_client(test_client, "other-user")
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def anonymous_client() -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


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
