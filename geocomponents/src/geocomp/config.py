"""Runtime configuration (env-driven, with sketch-friendly defaults)."""

from __future__ import annotations

import os
from pathlib import Path


def database_dsn() -> str:
    """libpq connection string for the PostGIS database."""
    return os.environ.get(
        "GEOCOMP_DSN",
        "host=localhost port=55432 dbname=geocomp user=geocomp password=geocomp",
    )


def descriptions_dir() -> Path:
    return Path(os.environ.get("GEOCOMP_DESCRIPTIONS", "descriptions"))


def public_base_url() -> str:
    """External base URL the API is reached at (for OGC hypermedia links)."""
    return os.environ.get("GEOCOMP_BASE_URL", "http://localhost:8000").rstrip("/")
