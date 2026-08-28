from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

SERVICE_NAME = "gcapi"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024
DEFAULT_SESSION_TTL_SECONDS = 600
DEFAULT_SESSION_COOKIE_NAME = "gcapi_session"
DEFAULT_SESSION_COOKIE_SAMESITE = "lax"


def _parse_positive_float(env_name: str, default: float) -> float:
    raw_value = os.environ.get(env_name)
    if raw_value is None:
        return default

    try:
        value = float(raw_value)
    except ValueError as err:
        raise RuntimeError(f"{env_name} must be a number") from err

    if value <= 0:
        raise RuntimeError(f"{env_name} must be greater than zero")
    return value


def _parse_positive_int(env_name: str, default: int) -> int:
    raw_value = os.environ.get(env_name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError as err:
        raise RuntimeError(f"{env_name} must be an integer") from err

    if value <= 0:
        raise RuntimeError(f"{env_name} must be greater than zero")
    return value


def _normalize_url(raw_value: str, env_name: str) -> str:
    value = raw_value.strip().rstrip("/")
    if not value:
        raise RuntimeError(f"{env_name} must be configured")

    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise RuntimeError(f"{env_name} must be an absolute http(s) URL")
    return value


def _required_url(env_name: str) -> str:
    raw_value = os.environ.get(env_name, "")
    if not raw_value.strip():
        raise RuntimeError(f"{env_name} must be configured")
    return _normalize_url(raw_value, env_name)


def _optional_url(env_name: str) -> str | None:
    raw_value = os.environ.get(env_name)
    if raw_value is None or not raw_value.strip():
        return None
    return _normalize_url(raw_value, env_name)


@dataclass(frozen=True)
class Settings:
    geocomponents_url: str
    gccore_url: str
    gcjobs_url: str | None = None
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS
    session_cookie_name: str = DEFAULT_SESSION_COOKIE_NAME
    session_cookie_secure: bool = False
    session_cookie_samesite: str = DEFAULT_SESSION_COOKIE_SAMESITE

    @classmethod
    def from_env(cls) -> Settings:
        session_cookie_samesite = (
            os.environ.get(
                "GCAPI_SESSION_COOKIE_SAMESITE",
                DEFAULT_SESSION_COOKIE_SAMESITE,
            )
            .strip()
            .lower()
        )
        if session_cookie_samesite not in {"lax", "strict", "none"}:
            raise RuntimeError(
                "GCAPI_SESSION_COOKIE_SAMESITE must be one of: lax, strict, none"
            )

        return cls(
            geocomponents_url=_required_url("GCAPI_GEOCOMPONENTS_URL"),
            gccore_url=_required_url("GCAPI_GCCORE_URL"),
            gcjobs_url=_optional_url("GCAPI_GCJOBS_URL"),
            request_timeout_seconds=_parse_positive_float(
                "GCAPI_REQUEST_TIMEOUT_SECONDS",
                DEFAULT_REQUEST_TIMEOUT_SECONDS,
            ),
            connect_timeout_seconds=_parse_positive_float(
                "GCAPI_CONNECT_TIMEOUT_SECONDS",
                DEFAULT_CONNECT_TIMEOUT_SECONDS,
            ),
            max_upload_bytes=_parse_positive_int(
                "GCAPI_MAX_UPLOAD_BYTES",
                DEFAULT_MAX_UPLOAD_BYTES,
            ),
            session_ttl_seconds=_parse_positive_int(
                "GCAPI_SESSION_TTL_SECONDS",
                DEFAULT_SESSION_TTL_SECONDS,
            ),
            session_cookie_name=os.environ.get(
                "GCAPI_SESSION_COOKIE_NAME",
                DEFAULT_SESSION_COOKIE_NAME,
            ).strip()
            or DEFAULT_SESSION_COOKIE_NAME,
            session_cookie_secure=(
                os.environ.get("GCAPI_SESSION_COOKIE_SECURE", "false").strip().lower()
                == "true"
            ),
            session_cookie_samesite=session_cookie_samesite,
        )
