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


def descriptions_dir() -> Path:
    return Path(os.environ.get("GEOCOMPONENTS_DESCRIPTIONS", "descriptions"))


def public_base_url() -> str:
    """External base URL the API is reached at (for OGC hypermedia links)."""
    return os.environ.get("GEOCOMPONENTS_BASE_URL", "http://localhost:8000").rstrip("/")
