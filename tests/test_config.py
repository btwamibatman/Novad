import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_development_settings_keep_local_cookie_name():
    test_settings = Settings(_env_file=None, environment="development")

    assert test_settings.is_production is False
    assert test_settings.session_cookie_name == "document_session"
    assert test_settings.allowed_host_list == ["localhost", "127.0.0.1", "testserver"]


def test_production_settings_use_host_only_cookie_name():
    test_settings = Settings(
        _env_file=None,
        environment="production",
        allowed_hosts="documents.example.com",
    )

    assert test_settings.is_production is True
    assert test_settings.session_cookie_name == "__Host-document_session"


def test_unknown_environment_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="prodution")


@pytest.mark.parametrize(
    "allowed_hosts",
    ["*", "localhost,127.0.0.1,testserver"],
)
def test_production_requires_explicit_public_allowed_host(allowed_hosts):
    with pytest.raises(ValidationError, match="explicit public ALLOWED_HOSTS"):
        Settings(
            _env_file=None,
            environment="production",
            allowed_hosts=allowed_hosts,
        )


def test_request_limit_must_allow_multipart_overhead():
    with pytest.raises(ValidationError, match="multipart overhead"):
        Settings(
            _env_file=None,
            max_upload_size_bytes=1024,
            max_request_size_bytes=1024,
        )
