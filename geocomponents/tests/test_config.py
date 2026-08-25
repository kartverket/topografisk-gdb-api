"""Executable spec for the DSN contract (pure unit; no database needed).

The connection is assembled from discrete ``DB_*`` env vars via
``psycopg.conninfo.make_conninfo`` (which escapes values), so we round-trip the
result through ``conninfo_to_dict`` to assert on the parsed keywords.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from psycopg.conninfo import conninfo_to_dict

from geocomponents import config

_ALL_DB_VARS = (
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_SSLMODE",
    "DB_SSLROOTCERT",
    "DB_SSLCERT",
    "DB_SSLKEY",
)


@pytest.fixture
def clean_env(monkeypatch):
    """Start from a known-empty DB_* environment for each test."""
    for var in _ALL_DB_VARS:
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_assembles_dsn_from_discrete_db_vars(clean_env):
    clean_env.setenv("DB_HOST", "10.0.0.5")
    clean_env.setenv("DB_PORT", "5432")
    clean_env.setenv("DB_NAME", "gc")
    clean_env.setenv("DB_USER", "svc")
    clean_env.setenv("DB_PASSWORD", "secret")

    parsed = conninfo_to_dict(config.database_dsn())
    assert parsed["host"] == "10.0.0.5"
    assert parsed["port"] == "5432"
    assert parsed["dbname"] == "gc"
    assert parsed["user"] == "svc"
    assert parsed["password"] == "secret"


def test_special_characters_in_password_round_trip(clean_env):
    # A secret-store password can contain characters that would corrupt a URL.
    weird = "p@ss/w:rd#x y"
    clean_env.setenv("DB_HOST", "h")
    clean_env.setenv("DB_NAME", "d")
    clean_env.setenv("DB_USER", "u")
    clean_env.setenv("DB_PASSWORD", weird)

    assert conninfo_to_dict(config.database_dsn())["password"] == weird


def test_ssl_keys_included_only_when_set(clean_env):
    clean_env.setenv("DB_HOST", "h")
    clean_env.setenv("DB_NAME", "d")
    clean_env.setenv("DB_USER", "u")
    clean_env.setenv("DB_PASSWORD", "p")

    assert "sslmode" not in conninfo_to_dict(config.database_dsn())

    clean_env.setenv("DB_SSLMODE", "verify-full")
    clean_env.setenv("DB_SSLROOTCERT", "/certs/ca.crt")
    parsed = conninfo_to_dict(config.database_dsn())
    assert parsed["sslmode"] == "verify-full"
    assert parsed["sslrootcert"] == "/certs/ca.crt"


def test_raises_when_unconfigured(clean_env):
    with pytest.raises(RuntimeError, match="DB_HOST"):
        config.database_dsn()


def test_descriptions_dir_defaults_to_shared_repo_folder(clean_env):
    clean_env.delenv("GEOCOMPONENTS_DESCRIPTIONS", raising=False)

    assert (
        config.descriptions_dir()
        == Path(__file__).resolve().parents[2] / "descriptions"
    )


def test_descriptions_dir_honors_env_override(clean_env):
    clean_env.setenv("GEOCOMPONENTS_DESCRIPTIONS", "/opt/custom-descriptions")

    assert config.descriptions_dir() == Path("/opt/custom-descriptions")
