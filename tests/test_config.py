import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_development_settings_keep_local_cookie_name():
    test_settings = Settings(_env_file=None, environment="development")

    assert test_settings.is_production is False
    assert test_settings.session_cookie_name == "document_session"


def test_production_settings_use_host_only_cookie_name():
    test_settings = Settings(_env_file=None, environment="production")

    assert test_settings.is_production is True
    assert test_settings.session_cookie_name == "__Host-document_session"


def test_unknown_environment_is_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="prodution")
