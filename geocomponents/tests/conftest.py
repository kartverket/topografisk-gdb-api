"""Shared fixtures for the DB-backed contract + integration suites.

The unit tests (loader/build/functions/config) need no database. These fixtures
back the ``tests/contract/`` and integration suites: they connect to PostGIS,
apply the schema once, and **skip** (rather than fail) if the database is
unreachable — so ``uv run pytest`` still runs the DB-free tests without Docker.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest

from geocomponents.config import database_dsn
from geocomponents.descriptions.loader import load_resolved_datasets
from geocomponents.schema import functions, postgis
from geocomponents.schema.build import build_schema_plan

DESCRIPTIONS_DIR = Path(__file__).resolve().parents[1] / "descriptions"

# Host-run tests target the local compose DB unless DB_* is already set (e.g. in
# CI). This lives in the test harness so production config stays fail-loud.
_COMPOSE_DSN = (
    "host=localhost port=55432 dbname=geocomponents "
    "user=geocomponents password=geocomponents"
)


def _test_dsn() -> str:
    return database_dsn() if "DB_HOST" in os.environ else _COMPOSE_DSN


@contextmanager
def _schema_conn(db: str, plan, *, with_functions: bool = True):
    """Drop schema, apply plan, yield an autocommit connection; drop schema on exit."""
    setup = psycopg.connect(db, autocommit=False)
    try:
        with setup.transaction():
            setup.execute(f"drop schema if exists {plan.schema_name} cascade")
        postgis.apply_tables(setup, plan)
        if with_functions:
            functions.apply_functions(setup, plan)
    finally:
        setup.close()
    conn = psycopg.connect(db, autocommit=True)
    try:
        yield conn
    finally:
        conn.execute(f"drop schema if exists {plan.schema_name} cascade")
        conn.close()


@pytest.fixture(scope="session")
def datasets():
    return load_resolved_datasets(DESCRIPTIONS_DIR)


@pytest.fixture(scope="session")
def db(datasets):
    """A DSN to a database with the schema applied; skips if DB is unreachable."""
    dsn = _test_dsn()
    try:
        conn = psycopg.connect(dsn, connect_timeout=2)
    except psycopg.OperationalError as err:
        pytest.skip(f"PostGIS not reachable ({err}); run `docker compose up -d db`")

    with conn:
        # Fresh slate so re-runs after signature changes don't leave stale overloads.
        conn.autocommit = True
        for d in datasets:
            conn.execute(f"drop schema if exists {d.name} cascade")
        conn.execute("drop schema if exists topogdb cascade")
        conn.execute("drop schema if exists ogc cascade")
        conn.autocommit = False
        functions.apply_topogdb(conn)
        functions.apply_dispatch(conn)
        for d in datasets:
            plan = build_schema_plan(d)
            postgis.apply_tables(conn, plan)
            functions.apply_functions(conn, plan)
    return dsn


@pytest.fixture(scope="module")
def conn(db):
    """A shared autocommit connection for one test module."""
    connection = psycopg.connect(db, autocommit=True)
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def conn_non_autocommit(db):
    """A fresh non-autocommit connection per test.

    Transaction state must not leak between these tests, and two of them exist
    specifically to verify what a failed transaction leaves behind.
    """
    connection = psycopg.connect(db, autocommit=False)
    try:
        yield connection
    finally:
        if not connection.closed:
            connection.rollback()
            connection.close()
