"""Integration test for ``apply_tables`` transaction / savepoint semantics."""

from __future__ import annotations

import psycopg
import pytest

from geocomponents.schema import postgis
from geocomponents.schema.plan import (
    CollectionPlan,
    ColumnPlan,
    ForeignKeyPlan,
    GeometryColumnPlan,
    SchemaPlan,
    TablePlan,
)


def _fk_plan(schema: str, table_names: list[str]) -> SchemaPlan:
    """Minimal SchemaPlan where each table has a self-referential FK."""
    colls = []
    for name in table_names:
        table = TablePlan(
            schema=schema,
            name=name,
            columns=(
                ColumnPlan(
                    "id",
                    "uuid",
                    nullable=False,
                    primary_key=True,
                    default="gen_random_uuid()",
                ),
                ColumnPlan("parent_id", "uuid"),
            ),
            geometry=GeometryColumnPlan("geometry", "Point", 4326),
            foreign_keys=(ForeignKeyPlan("parent_id", ref_table=f"{schema}.{name}"),),
        )
        colls.append(
            CollectionPlan(
                collection_name=name,
                feature_model="simple",
                table=table,
                functions={},  # apply_tables doesn't touch functions
            )
        )
    return SchemaPlan(schema_name=schema, collections=tuple(colls))


def test_table_statements_capture_changes_with_collection_metadata():
    ddl = "\n".join(postgis.table_statements(_fk_plan("roads", ["centreline"])))

    assert "create or replace function roads._centreline_record_change()" in ddl
    assert "after insert or update or delete on roads.centreline" in ddl
    assert "current_setting('geocomponents.suppress_change_events', true)" in ddl
    assert "'roads', 'centreline', 'create', NEW.\"id\"" in ddl
    assert 'null, NEW."geometry", 4326' in ddl
    assert "'roads', 'centreline', 'update', NEW.\"id\"" in ddl
    assert 'OLD."geometry", NEW."geometry", 4326' in ddl
    assert "'roads', 'centreline', 'delete', OLD.\"id\"" in ddl
    assert 'OLD."geometry", null, 4326' in ddl


def test_apply_tables_grown_plan_survives_duplicate_fk_from_prior_run(db):
    """Re-applying a grown plan (new collection added since last apply) must
    create the new table cleanly, even though the pre-existing FKs raise
    DuplicateObject partway through the run. If DuplicateObject aborted the
    whole transaction, the freshly created table would be rolled back and the
    follow-up ``ALTER TABLE <new_table> ADD CONSTRAINT`` would fail with
    UndefinedTable.
    """
    schema = "tx_repro"
    conn = psycopg.connect(db, autocommit=False)
    try:
        with conn.transaction():
            conn.execute(f"drop schema if exists {schema} cascade")

        # Step 1: apply small plan (table 'a' with self-FK).
        postgis.apply_tables(conn, _fk_plan(schema, ["a"]))

        # Step 2: apply grown plan (adds table 'b' with its own self-FK).
        # Old code: raises psycopg.errors.UndefinedTable during 'b's ALTER.
        # Fixed code: DuplicateObject on 'a's FK is savepoint-scoped, 'b' survives.
        postgis.apply_tables(conn, _fk_plan(schema, ["a", "b"]))

        with conn.transaction():
            rows = conn.execute(
                "select table_name from information_schema.tables "
                "where table_schema = %s order by table_name",
                (schema,),
            ).fetchall()
        assert [r[0] for r in rows] == ["a", "b", "collection_capability"]
    finally:
        try:
            with conn.transaction():
                conn.execute(f"drop schema if exists {schema} cascade")
        finally:
            conn.close()


def test_apply_tables_is_atomic_on_unexpected_error(db, monkeypatch):
    """An unexpected error mid-plan must roll the DB back to the pre-apply
    state — schema installs shouldn't half-apply."""
    schema = "tx_atomic"
    conn = psycopg.connect(db, autocommit=False)
    try:
        with conn.transaction():
            conn.execute(f"drop schema if exists {schema} cascade")

        # Inject a bogus statement after the CREATE TABLEs by monkeypatching
        # table_statements to append one that will fail with a non-DuplicateObject
        # error.
        original = postgis.table_statements

        def patched(plan):
            stmts = original(plan)
            # Insert a syntactically-invalid statement AFTER the table creates.
            stmts.append("this is not valid sql")
            return stmts

        monkeypatch.setattr(postgis, "table_statements", patched)

        with pytest.raises(psycopg.Error):
            postgis.apply_tables(conn, _fk_plan(schema, ["a"]))

        # After the failure, the whole schema apply should be rolled back:
        # the schema itself should not exist.
        with conn.transaction():
            rows = conn.execute(
                "select schema_name from information_schema.schemata "
                "where schema_name = %s",
                (schema,),
            ).fetchall()
        assert rows == [], f"schema '{schema}' leaked despite mid-apply failure"
    finally:
        try:
            with conn.transaction():
                conn.execute(f"drop schema if exists {schema} cascade")
        finally:
            conn.close()
