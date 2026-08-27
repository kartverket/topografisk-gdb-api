"""Write-path tests for association links (slice 2b).

Tests 1-8 and 13 are temporary: they read topology.association directly,
breaking the black-box rule (tests should observe behaviour through the
public API, not internal tables).  No read path exists yet, so direct table
access is the only way to assert links were written.  Slice C adds the read
path and retires these tests by rewriting against ogc.feature_item.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import psycopg
import pytest
import yaml

from geocomponents.descriptions.loader import resolve_dataset
from geocomponents.descriptions.models import Commons, DatasetDef
from geocomponents.schema import functions, postgis
from geocomponents.schema.build import build_schema_plan

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "topology_fixture.yaml"

# Pre-defined UUID constants for border features; outward identifier must be a uuid.
_B1A_ID = str(uuid.UUID(int=0xB1A))
_B1B_ID = str(uuid.UUID(int=0xB1B))
_B2_ID = str(uuid.UUID(int=0xB20))
_B1_DISPOSABLE_ID = str(uuid.UUID(int=0xD15))
_NO_SUCH_ID = str(uuid.UUID(int=0x999))  # valid UUID that matches no border

# Minimal valid geometries for the fixture collections (all SRID 4326, 2D).
_LINE_GEOM = {"type": "LineString", "coordinates": [[0, 0], [1, 0]]}
_POLYGON_GEOM = {
    "type": "MultiPolygon",
    "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]],
}


# --------------------------------------------------------------------------
# Fixture: topology schema with tables + functions
# --------------------------------------------------------------------------


def _load_plan():
    raw = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    return build_schema_plan(resolve_dataset(DatasetDef.model_validate(raw), Commons()))


@pytest.fixture(scope="module")
def topology_conn(db):
    """Apply topology schema (tables and functions); yield an autocommit connection."""
    plan = _load_plan()
    setup = psycopg.connect(db, autocommit=False)
    try:
        with setup.transaction():
            setup.execute(f"drop schema if exists {plan.schema_name} cascade")
        postgis.apply_tables(setup, plan)
        functions.apply_functions(setup, plan)
    finally:
        setup.close()

    conn = psycopg.connect(db, autocommit=True)
    try:
        yield conn
    finally:
        conn.execute(f"drop schema if exists {plan.schema_name} cascade")
        conn.close()


@pytest.fixture(scope="module")
def borders(topology_conn):
    """Create the border features shared across link tests.

    Returns a dict with the wire-format identifiers for each border:
      b1a_lokalid  lokalid of border1 #1  (wire key: 'lokalid')
      b1b_lokalid  lokalid of border1 #2  (wire key: 'lokalid')
      b2_lokalid   lokalid of border2     (wire key: 'lokalid')
      b3_id        uuid of border3        (wire key: 'id' — no outward identifier)
    """
    _txn(
        topology_conn,
        _insert("border1", _LINE_GEOM, {"identifikasjon": {"lokalid": _B1A_ID}}),
    )
    _txn(
        topology_conn,
        _insert("border1", _LINE_GEOM, {"identifikasjon": {"lokalid": _B1B_ID}}),
    )
    _txn(
        topology_conn,
        _insert("border2", _LINE_GEOM, {"identifikasjon": {"lokalid": _B2_ID}}),
    )
    b3 = _txn(topology_conn, _insert("border3", _LINE_GEOM, {}))
    return {
        "b1a_lokalid": _B1A_ID,
        "b1b_lokalid": _B1B_ID,
        "b2_lokalid": _B2_ID,
        "b3_id": b3["items"][0]["id"],
    }


# --------------------------------------------------------------------------
# Transaction helpers
# --------------------------------------------------------------------------


def _txn(conn, *items):
    """Run ogc.transaction('topology', ...) and return the JSON report."""
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


def _update(collection, fid, props):
    """PATCH: no geometry key → existing geometry kept unchanged."""
    return {
        "action": "update",
        "collection": collection,
        "id": fid,
        "feature": {"type": "Feature", "properties": props},
    }


def _replace(collection, fid, geom, props):
    """PUT: full document, all columns and link properties replaced."""
    return {
        "action": "replace",
        "collection": collection,
        "id": fid,
        "feature": {"type": "Feature", "geometry": geom, "properties": props},
    }


def _delete(collection, fid):
    return {"action": "delete", "collection": collection, "id": fid}


def _assoc_rows(conn, source_id):
    """Read (source_collection, property, target_id) for one source feature, sorted."""
    return conn.execute(
        "select source_collection, property, target_id::text "
        "from topology.association "
        "where source_id = %s::uuid "
        "order by property, target_id",
        (source_id,),
    ).fetchall()


def _assert_rejected(report):
    assert report["committed"] is False
    assert report["items"][0]["sqlstate"] == "P0001"


# Tests


def test_no_link_properties_collection_generates_unchanged_sql():
    """A collection with no declared link properties must generate the same
    SQL as before this slice: no _elem variable, no association reference.
    """
    from geocomponents.schema.functions import _fn_create, _fn_delete, _fn_update

    raw = {
        "name": "x",
        "collections": [{"name": "c", "geometry": {"type": "Point", "srid": 4326}}],
    }
    plan = build_schema_plan(resolve_dataset(DatasetDef.model_validate(raw), Commons()))
    coll = plan.collections[0]
    assert coll.roles == ()

    for op, fn in [
        ("create", _fn_create),
        ("update", _fn_update),
        ("delete", _fn_delete),
    ]:
        sql = fn(coll)
        assert "_elem" not in sql, f"{op}: link variable leaked"
        assert "association" not in sql, f"{op}: association reference leaked"


def test_wrong_featuretype_is_rejected(topology_conn, borders):
    """featuretype contradicting the declared target collection → P0001.

    surface.boundedByOuter declares target=border1; sending featuretype='wrong'
    is rejected before any row is written.
    """
    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "wrong", "lokalid": borders["b1a_lokalid"]}
                ],
            },
        ),
    )
    _assert_rejected(report)


def test_wrong_identifier_key_is_rejected(topology_conn, borders):
    """Using the wrong identifier key for a target → P0001.

    border1 is addressed by 'lokalid' (outward_identifier: identifikasjon.lokalid).
    Sending 'id' instead of 'lokalid' is rejected because the catalogue is authoritative.
    border3 is addressed by 'id'; sending 'lokalid' is also rejected (second case below).
    """
    # Case A: border1 expects 'lokalid'; sending 'id' is rejected
    report_a = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [{"featuretype": "border1", "id": str(uuid.uuid4())}],
            },
        ),
    )
    _assert_rejected(report_a)

    # Case B: border3 expects 'id'; sending 'lokalid' is rejected
    report_b = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "describedByNote": [{"featuretype": "border3", "lokalid": "ANYTHING"}],
            },
        ),
    )
    _assert_rejected(report_b)


def test_unknown_target_identifier_is_rejected(topology_conn, borders):
    """An identifier that no target row holds → P0001 (missing_member).

    _NO_SUCH_ID is a valid UUID that no border1 row holds.
    The item fails and no rows are written.
    """
    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [{"featuretype": "border1", "lokalid": _NO_SUCH_ID}],
            },
        ),
    )
    _assert_rejected(report)


def test_duplicate_target_is_rejected(topology_conn, borders):
    """The same target twice under one property → P0001.

    The association primary key makes (source, source_id, property, target_id) unique.
    Sending the same target twice is caught before inserting.
    """
    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]},
                    {
                        "featuretype": "border1",
                        "lokalid": borders["b1a_lokalid"],
                    },  # same target
                ],
            },
        ),
    )
    _assert_rejected(report)


def test_create_with_two_links_writes_two_rows(topology_conn, borders):
    """Two elements under one link property → two association rows, each a uuid.

    Finding two rows proves the lookup resolved the OI values to target row ids.
    Temporary: slice C retires this test once ogc.feature_item returns links.
    """
    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]},
                    {"featuretype": "border1", "lokalid": borders["b1b_lokalid"]},
                ],
            },
        ),
    )
    assert report["committed"] is True
    surface_id = report["items"][0]["id"]

    rows = _assoc_rows(topology_conn, surface_id)
    assert len(rows) == 2
    assert all(row[0] == "surface" for row in rows)
    assert all(row[1] == "boundedByOuter" for row in rows)
    # target_id is a uuid (not the lokaid text), proving a lookup was performed
    for row in rows:
        uuid.UUID(row[2])  # raises if not a valid uuid


def test_create_no_oi_target_by_uuid(topology_conn, borders):
    """A target with no outward_identifier is linked by its row uuid ('id' key)."""
    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "describedByNote": [{"featuretype": "border3", "id": borders["b3_id"]}],
            },
        ),
    )
    assert report["committed"] is True
    rows = _assoc_rows(topology_conn, report["items"][0]["id"])
    assert len(rows) == 1
    assert rows[0][1] == "describedByNote"


def test_update_leaves_unnamed_properties_intact(topology_conn, borders):
    """PATCH: a property absent from the document keeps its existing rows.

    Surface starts with rows under both boundedByOuter and boundedByShared.
    An update that only names boundedByShared must leave boundedByOuter untouched.
    Temporary: slice C retires this test once ogc.feature_item returns links.
    """
    create_report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]}
                ],
                "boundedByShared": [
                    {"featuretype": "border2", "lokalid": borders["b2_lokalid"]}
                ],
            },
        ),
    )
    surface_id = create_report["items"][0]["id"]

    _txn(topology_conn, _update("surface", surface_id, {"boundedByShared": []}))

    rows = _assoc_rows(topology_conn, surface_id)
    props = {row[1] for row in rows}
    assert "boundedByOuter" in props, "PATCH must not touch unmentioned properties"
    assert "boundedByShared" not in props, "named empty array clears that property"


def test_replace_clears_declared_properties_not_in_document(topology_conn, borders):
    """PUT: declared properties absent from the replace document are cleared.

    Surface starts with a boundedByOuter row. A replace that only names
    boundedByShared must clear boundedByOuter's rows entirely.
    Temporary: slice C retires this test once ogc.feature_item returns links.
    """
    create_report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]}
                ],
            },
        ),
    )
    surface_id = create_report["items"][0]["id"]

    _txn(
        topology_conn,
        _replace(
            "surface",
            surface_id,
            _POLYGON_GEOM,
            {
                "boundedByShared": [
                    {"featuretype": "border2", "lokalid": borders["b2_lokalid"]}
                ],
            },
        ),
    )

    rows = _assoc_rows(topology_conn, surface_id)
    props = {row[1] for row in rows}
    assert "boundedByOuter" not in props, (
        "PUT must clear declared-but-absent properties"
    )
    assert "boundedByShared" in props


def test_empty_array_clears_that_property(topology_conn, borders):
    """An empty array in the document clears that property's rows.

    An absent key (PATCH) means 'leave alone'; an empty array means 'remove all'.
    Temporary: slice C retires this test once ogc.feature_item returns links.
    """
    create_report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]}
                ],
            },
        ),
    )
    surface_id = create_report["items"][0]["id"]

    _txn(topology_conn, _update("surface", surface_id, {"boundedByOuter": []}))

    rows = _assoc_rows(topology_conn, surface_id)
    assert all(row[1] != "boundedByOuter" for row in rows)


def test_delete_source_removes_its_own_association_rows(topology_conn, borders):
    """Deleting a source feature removes all its association rows.

    A feature that no longer exists cannot reference anything; keeping orphaned
    source rows would make them unreportable.
    """
    create_report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]}
                ],
            },
        ),
    )
    surface_id = create_report["items"][0]["id"]

    _txn(topology_conn, _delete("surface", surface_id))

    assert _assoc_rows(topology_conn, surface_id) == []


def test_delete_target_leaves_inbound_rows_intact(topology_conn, borders):
    """Deleting a target feature does not remove inbound association rows.

    There is no FK on target_id by design: a dangling reference must remain
    reportable by phase 2a (slice C).  This test verifies no cascade was added.
    Temporary: slice C retires this test once ogc.feature_item returns links.
    """
    disposable_report = _txn(
        topology_conn,
        _insert(
            "border1", _LINE_GEOM, {"identifikasjon": {"lokalid": _B1_DISPOSABLE_ID}}
        ),
    )
    disposable_id = disposable_report["items"][0]["id"]

    create_report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": _B1_DISPOSABLE_ID}
                ],
            },
        ),
    )
    surface_id = create_report["items"][0]["id"]

    _txn(topology_conn, _delete("border1", disposable_id))

    rows = _assoc_rows(topology_conn, surface_id)
    assert len(rows) == 1, "Deleting a target must not remove inbound association rows"


def test_unlinking_does_not_modify_target_feature(topology_conn, borders):
    """Removing a link from a surface must not touch the target feature's row."""
    create_report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]}
                ],
            },
        ),
    )
    surface_id = create_report["items"][0]["id"]

    before = topology_conn.execute(
        'select updated_at from topology.border1 where "id" = %s::uuid',
        (borders["b1a_lokalid"],),
    ).fetchone()[0]

    _txn(topology_conn, _update("surface", surface_id, {"boundedByOuter": []}))

    after = topology_conn.execute(
        'select updated_at from topology.border1 where "id" = %s::uuid',
        (borders["b1a_lokalid"],),
    ).fetchone()[0]

    assert after == before, "Unlinking must not touch the target feature"


def test_reverse_and_idx_on_element_are_accepted(topology_conn, borders):
    """Link elements carrying 'reverse' and 'idx' are accepted; the extra keys
    are not stored anywhere.

    Real NGIS documents carry these on bounding-role elements. Ignoring them
    keeps the import path open without committing to their semantics.
    """
    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {
                        "featuretype": "border1",
                        "lokalid": borders["b1a_lokalid"],
                        "reverse": True,
                        "idx": [0, 0, 0],
                    }
                ],
            },
        ),
    )
    assert report["committed"] is True
    rows = _assoc_rows(topology_conn, report["items"][0]["id"])
    assert len(rows) == 1
    assert rows[0][1] == "boundedByOuter"


def test_upsert_rejects_declared_link_property(db):
    """ogc.feature_upsert raises P0001 for any declared link property.

    Silently dropping links on the bulk-import path would lose data without
    any error.  The generated _fn_upsert must reject before upserting.

    Uses a self-contained inline schema (not the topology fixture) so this
    test does not depend on the module-scoped topology_conn.
    """
    raw = {
        "name": "upsert_link_test",
        "collections": [
            {"name": "anchor", "geometry": {"type": "Point", "srid": 4326}},
            {
                "name": "doc",
                "geometry": {"type": "Point", "srid": 4326},
                "outward_identifier": "ext_id",
                "fields": [{"name": "ext_id", "type": "string"}],
                "relationships": [{"property": "linkedTo", "target": "anchor"}],
            },
        ],
    }
    plan = build_schema_plan(resolve_dataset(DatasetDef.model_validate(raw), Commons()))
    doc_plan = next(c for c in plan.collections if c.collection_name == "doc")
    assert doc_plan.upsert_field is not None
    assert doc_plan.roles

    setup = psycopg.connect(db, autocommit=False)
    try:
        with setup.transaction():
            setup.execute("drop schema if exists upsert_link_test cascade")
        postgis.apply_tables(setup, plan)
        functions.apply_functions(setup, plan)
    finally:
        setup.close()

    conn = psycopg.connect(db, autocommit=True)
    try:
        feature = json.dumps(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [0, 0]},
                "properties": {
                    "ext_id": "EX-1",
                    "linkedTo": [{"featuretype": "anchor", "id": str(uuid.uuid4())}],
                },
            }
        )
        with pytest.raises(psycopg.errors.RaiseException) as exc:
            conn.execute(
                "select upsert_link_test._doc_upsert(%s::jsonb)",
                (feature,),
            )
        assert exc.value.sqlstate == "P0001"
    finally:
        conn.execute("drop schema if exists upsert_link_test cascade")
        conn.close()
