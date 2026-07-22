"""Render + apply PostGIS table DDL from a ``SchemaPlan``.

This is one of only two PostgreSQL-specific modules (the other is
``functions.py``). Statement generation and application are kept separate so a
future migration emitter can reuse ``table_statements`` without executing it.

DDL is intentionally minimal/structural for now (column types, PK, geometry
type+SRID, FKs). Richer constraints (CHECK, code-list enforcement, nullability
on every attribute) are the deferred "validation in the DB" concern.
"""

from __future__ import annotations

import psycopg

from .plan import ColumnPlan, SchemaPlan, TablePlan

# PostgreSQL's NAMEDATALEN default. Identifiers longer than this are silently
# truncated by the server, so two distinct long names can collide.
_PG_MAX_IDENT_LEN = 63


def _column_ddl(col: ColumnPlan) -> str:
    parts = [f'"{col.name}"', col.sql_type]
    if col.primary_key:
        parts.append("primary key")
    if col.default is not None:
        parts.append(f"default {col.default}")
    if not col.nullable and not col.primary_key:
        parts.append("not null")
    return " ".join(parts)


def _table_ddl(table: TablePlan) -> str:
    lines = [_column_ddl(c) for c in table.columns]
    geom = table.geometry
    lines.append(f'"{geom.name}" geometry({geom.geometry_type}, {geom.srid})')
    cols = ",\n  ".join(lines)
    return f"create table if not exists {table.qualified} (\n  {cols}\n)"


def _fk_constraint_name(table_name: str, column: str) -> str:
    """Return the ``<t>_<c>_fkey`` name if it fits PG's 63-char identifier
    limit; otherwise raise ``ValueError``.
    """
    name = f"{table_name}_{column}_fkey"
    if len(name) > _PG_MAX_IDENT_LEN:
        raise ValueError(
            f"FK constraint name {name!r} is {len(name)} chars, exceeds PG's "
            f"{_PG_MAX_IDENT_LEN}-char identifier limit. Shorten the "
            f"collection ({table_name!r}) or relationship (that yielded column "
            f"{column!r}) name."
        )
    return name


def _fk_ddl(table: TablePlan) -> list[str]:
    stmts: list[str] = []
    for fk in table.foreign_keys:
        cname = _fk_constraint_name(table.name, fk.column)
        stmts.append(
            f"alter table {table.qualified} "
            f'add constraint "{cname}" '
            f'foreign key ("{fk.column}") '
            f'references {fk.ref_table} ("{fk.ref_column}") '
            f"on delete set null"
        )
    return stmts


def table_statements(plan: SchemaPlan) -> list[str]:
    """One complete SQL command per list element (idempotent where possible).

    FK constraints come after all tables so collection order and cross-collection
    cycles don't matter. Adding a constraint isn't ``IF NOT EXISTS``, so callers
    apply it defensively (see ``apply_tables``).
    """

    stmts: list[str] = [
        "create extension if not exists postgis",
        # gen_random_uuid() (id column default) is core in PG >= 13 but requires
        # pgcrypto on PG <= 12. Cheap portability; no-op on modern servers.
        "create extension if not exists pgcrypto",
        f"create schema if not exists {plan.schema_name}",
    ]
    for coll in plan.collections:
        stmts.append(_table_ddl(coll.table))
    for coll in plan.collections:
        stmts.extend(_fk_ddl(coll.table))
    return stmts


def render_tables(plan: SchemaPlan) -> str:
    """Human-readable DDL script (for inspection / future migrations)."""
    return ";\n\n".join(table_statements(plan)) + ";\n"


def apply_tables(conn: psycopg.Connection, plan: SchemaPlan) -> None:
    """Apply the plan atomically.

    Per-statement savepoints let re-runs tolerate ``DuplicateObject`` (e.g. an
    FK that already exists) without discarding earlier statements in the same
    transaction.
    """
    with conn.transaction():
        for stmt in table_statements(plan):
            try:
                with conn.transaction():
                    conn.execute(stmt)
            except psycopg.errors.DuplicateObject:
                # e.g. an FK constraint that already exists on re-application.
                continue
