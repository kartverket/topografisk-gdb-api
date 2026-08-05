"""Environment-backed configuration for the generic import service."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the importer."""

    api_url: str
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    request_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls, default_api_url: str) -> Settings:
        """Load and validate settings from the process environment."""
        api_url = os.environ.get("GCIMPORT_API_URL", default_api_url).strip()
        if not api_url:
            msg = "GCIMPORT_API_URL must not be empty"
            raise ValueError(msg)

        max_upload_bytes = _positive_int(
            "GCIMPORT_MAX_UPLOAD_BYTES",
            DEFAULT_MAX_UPLOAD_BYTES,
        )
        timeout = _positive_float("GCIMPORT_TIMEOUT_SECONDS", 30.0)
        return cls(
            api_url=api_url.rstrip("/"),
            max_upload_bytes=max_upload_bytes,
            request_timeout_seconds=timeout,
        )


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        value = default if raw is None else int(raw)
    except ValueError as err:
        msg = f"{name} must be a positive integer"
        raise ValueError(msg) from err
    if value <= 0:
        msg = f"{name} must be a positive integer"
        raise ValueError(msg)
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        value = default if raw is None else float(raw)
    except ValueError as err:
        msg = f"{name} must be a positive number"
        raise ValueError(msg) from err
    if value <= 0:
        msg = f"{name} must be a positive number"
        raise ValueError(msg)
    return value
