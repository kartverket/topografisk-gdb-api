from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import URL

SERVICE_NAME = "gcjobs"
DB_SCHEMA = "gc_jobs"

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


def redis_url() -> str:
    redis = os.environ.get("REDIS_URL", "").strip()
    if not redis:
        raise RuntimeError(f"No Redis configured for {SERVICE_NAME}: set REDIS_URL.")
    return redis


def gcimport_api_url() -> str:
    return os.environ.get("GCJOBS_IMPORT_API_URL", "http://localhost:8001").rstrip("/")
