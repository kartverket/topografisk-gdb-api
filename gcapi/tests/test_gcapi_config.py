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
    os.environ["GCAPI_PUBLIC_URL"] = "http://localhost:8004/"
    os.environ["GCAPI_GEOCOMPONENTS_URL"] = "http://localhost:8000"
    os.environ["GCAPI_GCJOBS_URL"] = "http://localhost:8003/"
    os.environ["GCAPI_REQUEST_TIMEOUT_SECONDS"] = "45"
    os.environ["GCAPI_CONNECT_TIMEOUT_SECONDS"] = "7.5"
    os.environ["GCAPI_MAX_UPLOAD_BYTES"] = "1234"

    settings = Settings.from_env()

    assert settings.public_url == "http://localhost:8004"
    assert settings.geocomponents_url == "http://localhost:8000"
    assert settings.gcjobs_url == "http://localhost:8003"
    assert settings.request_timeout_seconds == 45
    assert settings.connect_timeout_seconds == 7.5
    assert settings.max_upload_bytes == 1234


def test_settings_from_env_rejects_missing_required_url() -> None:
    os.environ["GCAPI_GEOCOMPONENTS_URL"] = "http://localhost:8000"
    os.environ["GCAPI_GCJOBS_URL"] = "http://localhost:8003"

    with pytest.raises(RuntimeError, match="GCAPI_PUBLIC_URL must be configured"):
        Settings.from_env()
