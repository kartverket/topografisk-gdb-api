"""Shared fixtures for the DB-backed contract + integration suites.

The unit tests (loader/build/functions/config) need no database. These fixtures
back the ``tests/contract/`` and integration suites: they connect to PostGIS,
apply the schema once, and **skip** (rather than fail) if the database is
unreachable — so ``uv run pytest`` still runs the DB-free tests without Docker.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg
import pytest
from fixtures.description_cache import resolved_datasets
from fixtures.simple_description import expected_simple_description

from geocomponents.config import database_dsn
from geocomponents.descriptions.loader import resolve_dataset
from geocomponents.descriptions.models import DatasetDef
from geocomponents.schema import functions, postgis
from geocomponents.schema.build import build_schema_plan


@pytest.fixture
def simple_description() -> dict:
    return expected_simple_description()


@pytest.fixture
def simple_dataset(simple_description):
    return resolve_dataset(DatasetDef.model_validate(simple_description))


# Host-run tests target the local compose DB unless DB_* is already set (e.g. in
# CI). This lives in the test harness so production config stays fail-loud.
_COMPOSE_DSN = (
    "host=localhost port=55432 dbname=geocomponents "
    "user=geocomponents password=geocomponents"
)


def _test_dsn() -> str:
    return database_dsn() if "DB_HOST" in os.environ else _COMPOSE_DSN


@contextmanager
def _schema_conn(
    db: str, plan, *, with_functions: bool = True, drop_on_exit: bool = True
):
    """Drop schema, apply plan, yield an autocommit connection; optionally drop on exit."""
    if with_functions:
        functions.function_statements(plan)
    conn = psycopg.connect(db, autocommit=False)
    try:
        with conn.transaction():
            conn.execute(
                psycopg.sql.SQL("drop schema if exists {} cascade").format(
                    psycopg.sql.Identifier(plan.schema_name)
                )
            )
        postgis.apply_tables(conn, plan)
        if with_functions:
            functions.apply_functions(conn, plan)
        conn.autocommit = True
        yield conn
    finally:
        if not conn.closed:
            if drop_on_exit:
                conn.execute(
                    psycopg.sql.SQL("drop schema if exists {} cascade").format(
                        psycopg.sql.Identifier(plan.schema_name)
                    )
                )
            conn.close()


@pytest.fixture(scope="session")
def datasets():
    return resolved_datasets()


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
            conn.execute(
                psycopg.sql.SQL("drop schema if exists {} cascade").format(
                    psycopg.sql.Identifier(d.name)
                )
            )
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
