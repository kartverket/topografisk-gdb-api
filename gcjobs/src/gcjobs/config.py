from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import URL

SERVICE_NAME = "gcjobs"
DB_SCHEMA = "gc_jobs"
# Keep synchronized with gcimport.profiles.BUILTIN_PROFILES without creating a runtime dependency.
SUPPORTED_IMPORT_PROFILES = frozenset({"fkb_bane", "bygning"})
DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024
_REPO_ROOT = Path(__file__).resolve().parents[3]

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

_REQUIRED_DB_VARS = ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")


def _database_env() -> dict[str, str]:
    missing = [var for var in _REQUIRED_DB_VARS if not os.environ.get(var)]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            f"No database configured for {SERVICE_NAME}: set {names} and related DB_* variables."
        )
    env = {var: os.environ[var] for var, _keyword in _DB_PARTS if os.environ.get(var)}
    env.setdefault("DB_PORT", "5432")
    return env


def psycopg_dsn() -> str:
    from psycopg.conninfo import make_conninfo

    env = _database_env()
    params = {keyword: env[var] for var, keyword in _DB_PARTS if env.get(var)}
    return make_conninfo(**params)


def sqlalchemy_url() -> str:
    env = _database_env()
    query = {
        key.removeprefix("DB_").lower(): value
        for key, value in env.items()
        if key in {"DB_SSLMODE", "DB_SSLROOTCERT", "DB_SSLCERT", "DB_SSLKEY"}
    }
    return URL.create(
        "postgresql+psycopg",
        username=env["DB_USER"],
        password=env["DB_PASSWORD"],
        host=env["DB_HOST"],
        port=int(env["DB_PORT"]),
        database=env["DB_NAME"],
        query=query,
    ).render_as_string(hide_password=False)


def alembic_dir() -> Path:
    return Path(__file__).resolve().parent / "alembic"


def descriptions_dir() -> Path:
    if configured := os.environ.get("GEOCOMPONENTS_DESCRIPTIONS"):
        return Path(configured)

    shared_repo_descriptions = _REPO_ROOT / "descriptions"
    if shared_repo_descriptions.exists():
        return shared_repo_descriptions

    return Path("descriptions")


def public_base_url() -> str:
    return os.environ.get("GCJOBS_BASE_URL", "http://localhost:8000").rstrip("/")


def redis_url() -> str:
    redis = os.environ.get("REDIS_URL", "").strip()
    if not redis:
        raise RuntimeError(f"No Redis configured for {SERVICE_NAME}: set REDIS_URL.")
    return redis


def gcimport_api_url() -> str:
    return os.environ.get("GCJOBS_IMPORT_API_URL", "http://localhost:8001").rstrip("/")


def max_upload_bytes() -> int:
    raw_value = os.environ.get("GCJOBS_MAX_UPLOAD_BYTES")
    if raw_value is None:
        return DEFAULT_MAX_UPLOAD_BYTES

    try:
        value = int(raw_value)
    except ValueError as err:
        raise RuntimeError("GCJOBS_MAX_UPLOAD_BYTES must be an integer") from err

    if value <= 0:
        raise RuntimeError("GCJOBS_MAX_UPLOAD_BYTES must be greater than zero")
    return value
