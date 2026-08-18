"""Environment-backed configuration for the generic import service."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024
DEFAULT_UPSERT_BATCH_SIZE = 250


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the importer."""

    geocomponents_api_url: str
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    request_timeout_seconds: float = 30.0
    upsert_batch_size: int = DEFAULT_UPSERT_BATCH_SIZE

    @classmethod
    def from_env(cls) -> Settings:
        """Load and validate settings from the process environment."""
        geocomponents_api_url = os.environ.get("GEOCOMPONENTS_API_URL", "").strip()
        if not geocomponents_api_url:
            msg = "GEOCOMPONENTS_API_URL must be set"
            raise ValueError(msg)

        max_upload_bytes = _positive_int(
            "GCIMPORT_MAX_UPLOAD_BYTES",
            DEFAULT_MAX_UPLOAD_BYTES,
        )
        timeout = _positive_float("GCIMPORT_TIMEOUT_SECONDS", 30.0)
        upsert_batch_size = _positive_int(
            "GCIMPORT_UPSERT_BATCH_SIZE",
            DEFAULT_UPSERT_BATCH_SIZE,
        )
        return cls(
            geocomponents_api_url=geocomponents_api_url.rstrip("/"),
            max_upload_bytes=max_upload_bytes,
            request_timeout_seconds=timeout,
            upsert_batch_size=upsert_batch_size,
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
