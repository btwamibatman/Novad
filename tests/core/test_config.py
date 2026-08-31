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


def test_pdf_page_limit_must_be_positive():
    with pytest.raises(ValidationError, match="MAX_PDF_PAGES must be greater than zero"):
        Settings(_env_file=None, max_pdf_pages=0)


def test_ai_job_defaults_and_api_key_repr_are_safe():
    test_settings = Settings(_env_file=None, gemini_api_key="top-secret")

    assert test_settings.ai_job_max_attempts == 4
    assert test_settings.ai_max_pdf_bytes == 50 * 1024 * 1024
    assert test_settings.ai_file_processing_timeout_seconds == 120
    assert test_settings.ai_job_stale_seconds == 300
    assert test_settings.ai_retry_base_seconds == 5
    assert test_settings.ai_provider_min_request_interval_seconds == 12
    assert test_settings.gemini_service_tier == "unpaid"
    assert "top-secret" not in repr(test_settings)


def test_ai_job_stale_timeout_must_be_positive():
    with pytest.raises(ValidationError, match="AI_JOB_STALE_SECONDS"):
        Settings(_env_file=None, ai_job_stale_seconds=0)


def test_ai_file_processing_timeout_must_be_positive():
    with pytest.raises(ValidationError, match="AI_FILE_PROCESSING_TIMEOUT_SECONDS"):
        Settings(_env_file=None, ai_file_processing_timeout_seconds=0)


def test_ai_pdf_limit_must_be_positive():
    with pytest.raises(ValidationError, match="AI_MAX_PDF_BYTES"):
        Settings(_env_file=None, ai_max_pdf_bytes=0)
