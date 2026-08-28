from __future__ import annotations

import os

import pytest

from gcapi.config import Settings


@pytest.fixture(autouse=True)
def clear_gcapi_env() -> None:
    keys = [key for key in os.environ if key.startswith("GCAPI_")]
    for key in keys:
        os.environ.pop(key, None)


def test_settings_from_env_parses_required_and_optional_values() -> None:
    os.environ["GCAPI_GEOCOMPONENTS_URL"] = "http://localhost:8000"
    os.environ["GCAPI_GCCORE_URL"] = "http://localhost:8002"
    os.environ["GCAPI_GCJOBS_URL"] = "http://localhost:8003"
    os.environ["GCAPI_REQUEST_TIMEOUT_SECONDS"] = "45"
    os.environ["GCAPI_CONNECT_TIMEOUT_SECONDS"] = "7.5"
    os.environ["GCAPI_MAX_UPLOAD_BYTES"] = "1234"
    os.environ["GCAPI_SESSION_TTL_SECONDS"] = "600"
    os.environ["GCAPI_SESSION_COOKIE_NAME"] = "dev_session"
    os.environ["GCAPI_SESSION_COOKIE_SECURE"] = "true"
    os.environ["GCAPI_SESSION_COOKIE_SAMESITE"] = "strict"

    settings = Settings.from_env()

    assert settings.geocomponents_url == "http://localhost:8000"
    assert settings.gccore_url == "http://localhost:8002"
    assert settings.gcjobs_url == "http://localhost:8003"
    assert settings.request_timeout_seconds == 45
    assert settings.connect_timeout_seconds == 7.5
    assert settings.max_upload_bytes == 1234
    assert settings.session_ttl_seconds == 600
    assert settings.session_cookie_name == "dev_session"
    assert settings.session_cookie_secure is True
    assert settings.session_cookie_samesite == "strict"


def test_settings_from_env_leaves_gcjobs_url_unset_when_missing() -> None:
    os.environ["GCAPI_GEOCOMPONENTS_URL"] = "http://localhost:8000"
    os.environ["GCAPI_GCCORE_URL"] = "http://localhost:8002"

    settings = Settings.from_env()

    assert settings.gcjobs_url is None


def test_settings_from_env_rejects_missing_required_url() -> None:
    with pytest.raises(
        RuntimeError, match="GCAPI_GEOCOMPONENTS_URL must be configured"
    ):
        Settings.from_env()


def test_settings_from_env_rejects_missing_gccore_url() -> None:
    os.environ["GCAPI_GEOCOMPONENTS_URL"] = "http://localhost:8000"

    with pytest.raises(RuntimeError, match="GCAPI_GCCORE_URL must be configured"):
        Settings.from_env()


def test_settings_from_env_rejects_invalid_cookie_samesite() -> None:
    os.environ["GCAPI_GEOCOMPONENTS_URL"] = "http://localhost:8000"
    os.environ["GCAPI_GCCORE_URL"] = "http://localhost:8002"
    os.environ["GCAPI_SESSION_COOKIE_SAMESITE"] = "invalid"

    with pytest.raises(
        RuntimeError,
        match="GCAPI_SESSION_COOKIE_SAMESITE must be one of: lax, strict, none",
    ):
        Settings.from_env()
