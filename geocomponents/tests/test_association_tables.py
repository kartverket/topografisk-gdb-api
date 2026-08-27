"""DB contract tests for the association_role and association tables (slice 2a).

These tests prove that the description generates exactly the schema it claims to
(§4.1 of topology_plan.md) and that the guard against unsafe property removal
works before any write path exists.
"""

from __future__ import annotations

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


# --------------------------------------------------------------------------
# Shared setup
# --------------------------------------------------------------------------


def _load_topology_plan():
    raw = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    return build_schema_plan(resolve_dataset(DatasetDef.model_validate(raw), Commons()))


@pytest.fixture(scope="module")
def topology_conn(db):
    """Apply the topology fixture schema; yield an autocommit connection."""
    with _schema_conn(db, _load_topology_plan(), with_functions=False) as conn:
        yield conn


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
# Expected golden data
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


def test_catalogue_contents_match_golden_table(topology_conn):
    """Catalogue rows after apply-schema match §6 of topology_plan.md exactly."""
    rows = topology_conn.execute(
        "select source_collection, property, target_collection "
        "from topology.association_role "
        "order by source_collection, property"
    ).fetchall()
    actual = [RoleRow(*r) for r in rows]
    assert _render_role_rows(actual) == _render_role_rows(_EXPECTED_ROLE_ROWS)


def test_association_and_role_column_shapes(topology_conn):
    """Column names, types, and nullability match §4.1, sorted by name."""

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
    """A dataset with no relationships gets no association tables (test 4)."""
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
    property (test 5).

    NOTE: inserts directly into association because no write path exists yet.
    Slice B or C should replace this direct insert once links can be written
    through ogc.*.
    """
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()
    topology_conn.execute(
        "insert into topology.association "
        "(source_collection, source_id, property, target_id) "
        "values ('surface', %s, 'boundedByOuter', %s)",
        (source_id, target_id),
    )

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
            "where source_collection = 'surface' and property = 'boundedByOuter'"
        ).fetchone()[0]
        assert count == 1
    finally:
        topology_conn.execute("delete from topology.association")


def test_association_has_no_target_collection_column(topology_conn):
    """association carries no target_collection; the catalogue is the authority
    (test 6). Also verifies association_role has no unique constraint beyond
    its primary key.
    """
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
    """A relationship whose target is not a collection in the dataset is
    rejected by resolve_dataset, not silently accepted (test 7).
    """
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
