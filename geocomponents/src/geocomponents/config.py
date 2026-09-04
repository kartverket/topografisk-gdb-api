"""Runtime configuration.

The database connection is assembled from discrete ``DB_*`` environment variables
-- the single mechanism used everywhere (``docker-compose`` locally, the apps-repo
Deployment in production, and the test harness):

    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD          (DB_PASSWORD from a
    DB_SSLMODE, DB_SSLROOTCERT, DB_SSLCERT, DB_SSLKEY         secret store; SSL
                                                              optional)

``make_conninfo`` builds the libpq DSN and escapes values, so a secret-store
password containing special characters is handled correctly. If ``DB_HOST`` is
unset, ``database_dsn()`` raises rather than silently defaulting to localhost --
misconfiguration should fail loudly. Local development runs via ``docker compose
up`` (which sets the ``DB_*`` vars); see the README.
"""

from __future__ import annotations

import os
from pathlib import Path

SERVICE_NAME = "geocomponents"
DEFAULT_EVENT_POLL_SECONDS = 1.0
DEFAULT_EVENT_BATCH_SIZE = 100
DEFAULT_EVENT_CLAIM_TIMEOUT_SECONDS = 30.0
DEFAULT_EVENT_STREAM_MAXLEN = 10_000

_REPO_ROOT = Path(__file__).resolve().parents[3]

# DB_* var -> libpq keyword. Included in the DSN only when the var is set.
_DB_PARTS = (
    ("DB_HOST", "host"),
    ("DB_PORT", "port"),
    ("DB_NAME", "dbname"),
    ("DB_USER", "user"),
    ("DB_PASSWORD", "password"),
    ("DB_SSLMODE", "sslmode"),
    ("DB_SSLROOTCERT", "sslrootcert"),
    ("DB_SSLCERT", "sslcert"),
    ("DB_SSLKEY", "sslkey"),
)


def database_dsn() -> str:
    """Assemble the libpq DSN from the discrete ``DB_*`` vars (see module docstring)."""
    if "DB_HOST" not in os.environ:
        raise RuntimeError(
            "No database configured: set the DB_* variables "
            "(DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, ...). "
            "For local development use `docker compose up` (see the README)."
        )
    # make_conninfo handles libpq escaping of values.
    from psycopg.conninfo import make_conninfo

    params = {
        keyword: os.environ[var] for var, keyword in _DB_PARTS if os.environ.get(var)
    }
    return make_conninfo(**params)


def redis_url() -> str:
    value = os.environ.get("REDIS_URL", "").strip()
    if not value:
        raise RuntimeError(f"No Redis configured for {SERVICE_NAME}: set REDIS_URL.")
    return value


def _positive_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as err:
        raise RuntimeError(f"{name} must be a number") from err
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


def _positive_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as err:
        raise RuntimeError(f"{name} must be an integer") from err
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


def event_poll_seconds() -> float:
    return _positive_float(
        "GEOCOMPONENTS_EVENT_POLL_SECONDS", DEFAULT_EVENT_POLL_SECONDS
    )


def event_batch_size() -> int:
    return _positive_int("GEOCOMPONENTS_EVENT_BATCH_SIZE", DEFAULT_EVENT_BATCH_SIZE)


def event_claim_timeout_seconds() -> float:
    return _positive_float(
        "GEOCOMPONENTS_EVENT_CLAIM_TIMEOUT_SECONDS",
        DEFAULT_EVENT_CLAIM_TIMEOUT_SECONDS,
    )


def event_stream_maxlen() -> int:
    return _positive_int(
        "GEOCOMPONENTS_EVENT_STREAM_MAXLEN", DEFAULT_EVENT_STREAM_MAXLEN
    )


def descriptions_dir() -> Path:
    if configured := os.environ.get("GEOCOMPONENTS_DESCRIPTIONS"):
        return Path(configured)

    shared_repo_descriptions = _REPO_ROOT / "descriptions"
    if shared_repo_descriptions.exists():
        return shared_repo_descriptions

    return Path("descriptions")


def public_base_url() -> str:
    """External base URL the API is reached at (for OGC hypermedia links)."""
    return os.environ.get("GEOCOMPONENTS_BASE_URL", "http://localhost:8000").rstrip("/")
