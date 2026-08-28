"""DB contract tests for the association_role and association tables (slice 2a).

These tests prove that the description generates exactly the schema it claims to
(§4.1 of topology_plan.md) and that the guard against unsafe property removal
still works once links are written through the public surface.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
import yaml
from conftest import _schema_conn

from geocomponents.descriptions.loader import resolve_dataset
from geocomponents.descriptions.models import Commons, DatasetDef
from geocomponents.schema import postgis
from geocomponents.schema.build import build_schema_plan

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "topology_fixture.yaml"
_BORDER_ID = str(uuid.UUID(int=0xB1A))
_LINE_GEOM = {"type": "LineString", "coordinates": [[0, 0], [1, 0]]}
_POLYGON_GEOM = {
    "type": "MultiPolygon",
    "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]],
}


# --------------------------------------------------------------------------
# Shared setup
# --------------------------------------------------------------------------


def _load_topology_plan():
    raw = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    return build_schema_plan(resolve_dataset(DatasetDef.model_validate(raw), Commons()))


@pytest.fixture(scope="module")
def topology_conn(db):
    """Apply the topology fixture schema; yield an autocommit connection."""
    with _schema_conn(db, _load_topology_plan(), with_functions=True) as conn:
        yield conn


def _txn(conn, *items):
    doc = {"semantic": "atomic", "transaction": list(items)}
    return conn.execute(
        "select ogc.transaction('topology', %s::jsonb)",
        (json.dumps(doc),),
    ).fetchone()[0]


def _insert(collection, geom, props):
    return {
        "action": "insert",
        "collection": collection,
        "feature": {"type": "Feature", "geometry": geom, "properties": props},
    }


def _delete(collection, fid):
    return {"action": "delete", "collection": collection, "id": fid}


# --------------------------------------------------------------------------
# Golden-table helpers
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RoleRow:
    source_collection: str
    property: str
    target_collection: str


@dataclass(frozen=True)
class ColumnInfo:
    column_name: str
    data_type: str
    is_nullable: str


def _render_role_rows(rows: list[RoleRow]) -> str:
    header = f"{'source_collection':<20} {'property':<20} {'target_collection'}"
    sep = "-" * len(header)
    lines = [header, sep]
    for r in sorted(rows, key=lambda r: (r.source_collection, r.property)):
        lines.append(
            f"{r.source_collection:<20} {r.property:<20} {r.target_collection}"
        )
    return "\n".join(lines)


def _render_column_info(rows: list[ColumnInfo]) -> str:
    header = f"{'column_name':<22} {'data_type':<10} is_nullable"
    sep = "-" * len(header)
    lines = [header, sep]
    for r in sorted(rows, key=lambda r: r.column_name):
        lines.append(f"{r.column_name:<22} {r.data_type:<10} {r.is_nullable}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Expected
# --------------------------------------------------------------------------

_EXPECTED_ROLE_ROWS: list[RoleRow] = [
    RoleRow("surface", "boundedByOuter", "border1"),
    RoleRow("surface", "boundedByShared", "border2"),
    RoleRow("surface", "describedByNote", "border3"),
    RoleRow("surface2", "boundedByOuter", "border1"),
]

_EXPECTED_ROLE_COLUMNS: list[ColumnInfo] = [
    ColumnInfo("property", "text", "NO"),
    ColumnInfo("source_collection", "text", "NO"),
    ColumnInfo("target_collection", "text", "NO"),
]

_EXPECTED_ASSOC_COLUMNS: list[ColumnInfo] = [
    ColumnInfo("property", "text", "NO"),
    ColumnInfo("source_collection", "text", "NO"),
    ColumnInfo("source_id", "uuid", "NO"),
    ColumnInfo("target_id", "uuid", "NO"),
]


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


def test_catalogue_rows_expected(topology_conn):
    rows = topology_conn.execute(
        "select source_collection, property, target_collection "
        "from topology.association_role "
        "order by source_collection, property"
    ).fetchall()
    actual = [RoleRow(*r) for r in rows]
    assert _render_role_rows(actual) == _render_role_rows(_EXPECTED_ROLE_ROWS)


def test_association_and_role_column_shapes(topology_conn):
    """Column names, types, and nullability sorted by name."""

    def _columns(table: str) -> list[ColumnInfo]:
        rows = topology_conn.execute(
            "select column_name, data_type, is_nullable "
            "from information_schema.columns "
            "where table_schema = 'topology' and table_name = %s "
            "order by column_name",
            (table,),
        ).fetchall()
        return [ColumnInfo(*r) for r in rows]

    assert _render_column_info(_columns("association_role")) == _render_column_info(
        _EXPECTED_ROLE_COLUMNS
    )
    assert _render_column_info(_columns("association")) == _render_column_info(
        _EXPECTED_ASSOC_COLUMNS
    )


def test_constraints_are_canonical(topology_conn):
    """Constraints via pg_get_constraintdef match the declared primary key and
    foreign key; Postgres regenerates this string so it is canonical.
    """

    def _constraints(table: str) -> list[str]:
        return sorted(
            row[0]
            for row in topology_conn.execute(
                "select pg_get_constraintdef(oid) "
                "from pg_constraint "
                "where conrelid = %s::regclass",
                (f"topology.{table}",),
            ).fetchall()
        )

    assert _constraints("association_role") == [
        "PRIMARY KEY (source_collection, property)",
    ]
    assert _constraints("association") == sorted(
        [
            "PRIMARY KEY (source_collection, source_id, property, target_id)",
            "FOREIGN KEY (source_collection, property) "
            "REFERENCES association_role(source_collection, property)",
        ]
    )


def test_dataset_with_no_relationships_applies_cleanly(db):
    """A dataset with no relationships gets no association tables"""
    raw = {
        "name": "no_rels",
        "collections": [{"name": "item", "geometry": {"type": "Point", "srid": 4326}}],
    }
    plan = build_schema_plan(resolve_dataset(DatasetDef.model_validate(raw), Commons()))
    assert plan.association_role_rows == ()

    conn = psycopg.connect(db, autocommit=False)
    try:
        with conn.transaction():
            conn.execute("drop schema if exists no_rels cascade")
        postgis.apply_tables(conn, plan)
        exists = conn.execute(
            "select 1 from information_schema.tables "
            "where table_schema = 'no_rels' and table_name = 'association_role'"
        ).fetchone()
        assert exists is None
    finally:
        with conn.transaction():
            conn.execute("drop schema if exists no_rels cascade")
        conn.close()


def test_guard_aborts_when_referenced_property_removed(topology_conn, db):
    """apply-schema aborts unchanged when association rows reference a removed
    property"""
    source_id = None
    target_id = None
    target_report = _txn(
        topology_conn,
        _insert("border1", _LINE_GEOM, {"identifikasjon": {"lokalid": _BORDER_ID}}),
    )
    assert target_report["committed"] is True
    target_id = target_report["items"][0]["id"]

    source_report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {"boundedByOuter": [{"featuretype": "border1", "lokalid": _BORDER_ID}]},
        ),
    )
    assert source_report["committed"] is True
    source_id = source_report["items"][0]["id"]

    try:
        raw = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
        # Remove boundedByOuter from surface
        surface = next(c for c in raw["collections"] if c["name"] == "surface")
        surface["relationships"] = [
            r for r in surface["relationships"] if r["property"] != "boundedByOuter"
        ]
        stripped_plan = build_schema_plan(
            resolve_dataset(DatasetDef.model_validate(raw), Commons())
        )

        apply_conn = psycopg.connect(db, autocommit=True)
        try:
            with pytest.raises(RuntimeError, match="association"):
                postgis.apply_tables(apply_conn, stripped_plan)
        finally:
            apply_conn.close()

        # Original row must still be there — nothing was changed
        count = topology_conn.execute(
            "select count(*) from topology.association "
            "where source_collection = 'surface' and property = 'boundedByOuter' "
            "and source_id = %s::uuid",
            (source_id,),
        ).fetchone()[0]
        assert count == 1
    finally:
        if source_id is not None:
            _txn(topology_conn, _delete("surface", source_id))
        if target_id is not None:
            _txn(topology_conn, _delete("border1", target_id))


def test_association_has_no_target_collection_column(topology_conn):
    """Potentially covered by catalogue expected"""
    col_names = {
        row[0]
        for row in topology_conn.execute(
            "select column_name from information_schema.columns "
            "where table_schema = 'topology' and table_name = 'association'"
        ).fetchall()
    }
    assert "target_collection" not in col_names

    # No unique constraint (type 'u') on association_role — only the PK (type 'p')
    unique_constraints = topology_conn.execute(
        "select 1 from pg_constraint "
        "where conrelid = 'topology.association_role'::regclass and contype = 'u'"
    ).fetchall()
    assert unique_constraints == []


def test_relationship_target_not_in_dataset_rejected_at_load_time():
    from geocomponents.descriptions.loader import DescriptionError

    raw = {
        "name": "x",
        "collections": [
            {
                "name": "c",
                "geometry": {"type": "Point", "srid": 4326},
                "relationships": [{"property": "link", "target": "ghost"}],
            }
        ],
    }
    with pytest.raises(DescriptionError, match="unknown collection 'ghost'"):
        resolve_dataset(DatasetDef.model_validate(raw), Commons())
