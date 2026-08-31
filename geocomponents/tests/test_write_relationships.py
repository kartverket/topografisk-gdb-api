"""Contract tests for association links on the transaction and read paths."""

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
from geocomponents.schema import functions, postgis
from geocomponents.schema.build import build_schema_plan

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "topology_fixture.yaml"

# Minimal valid geometries for the fixture collections (all SRID 4326, 2D).
_LINE_GEOM = {"type": "LineString", "coordinates": [[0, 0], [1, 0]]}
_LINE_GEOM_ALT = {"type": "LineString", "coordinates": [[10, 0], [11, 0]]}
_LINE_GEOM_ALT_2 = {"type": "LineString", "coordinates": [[20, 0], [21, 0]]}
_POLYGON_GEOM = {
    "type": "MultiPolygon",
    "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]],
}


def _new_id():
    return str(uuid.uuid4())


@dataclass(frozen=True)
class StructuralFailureCase:
    setup_items: tuple[dict, ...]
    tx_items: tuple[dict, ...]
    expected_findings: tuple[dict, ...]
    expected_present: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class StructuralSuccessCase:
    setup_items: tuple[dict, ...]
    tx_items: tuple[dict, ...]
    expected_association_clears: tuple[tuple[str, str], ...] = ()


# --------------------------------------------------------------------------
# Fixture: topology schema with tables + functions
# --------------------------------------------------------------------------


def _load_plan():
    raw = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    return build_schema_plan(resolve_dataset(DatasetDef.model_validate(raw), Commons()))


@pytest.fixture(scope="module")
def topology_conn(db):
    """Apply topology schema (tables and functions); yield an autocommit connection."""
    with _schema_conn(db, _load_plan()) as conn:
        yield conn


@pytest.fixture(scope="module")
def borders(topology_conn):
    """Create the border features shared across link tests.

    Returns a dict with the wire-format identifiers for each border:
      b1a_lokalid  lokalid of border1 #1  (wire key: 'lokalid')
      b1b_lokalid  lokalid of border1 #2  (wire key: 'lokalid')
      b2_lokalid   lokalid of border2     (wire key: 'lokalid')
      b3_id        uuid of border3        (wire key: 'id' — no outward identifier)
    """
    b1a_id, b1b_id = sorted([_new_id(), _new_id()])
    b2_id = _new_id()
    _txn(
        topology_conn,
        _insert("border1", _LINE_GEOM, {"identifikasjon": {"lokalid": b1a_id}}),
    )
    _txn(
        topology_conn,
        _insert("border1", _LINE_GEOM, {"identifikasjon": {"lokalid": b1b_id}}),
    )
    _txn(
        topology_conn,
        _insert("border2", _LINE_GEOM, {"identifikasjon": {"lokalid": b2_id}}),
    )
    b3 = _txn(topology_conn, _insert("border3", _LINE_GEOM, {}))
    return {
        "b1a_lokalid": b1a_id,
        "b1b_lokalid": b1b_id,
        "b2_lokalid": b2_id,
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


def _insert(collection, geom, props, *, fid=None):
    feature = {"type": "Feature", "geometry": geom, "properties": props}
    if fid is not None:
        feature["id"] = fid
    return {
        "action": "insert",
        "collection": collection,
        "feature": feature,
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


def _item(conn, collection, fid):
    """Read one feature through the public OGC function."""
    return conn.execute(
        "select ogc.feature_item('topology', %s, %s::uuid)",
        (collection, fid),
    ).fetchone()[0]


def _items(conn, collection, lim=1000):
    """Read a feature collection through the public OGC function."""
    return conn.execute(
        "select ogc.feature_items('topology', %s, %s, %s, %s, %s)",
        (collection, None, lim, 0, True),
    ).fetchone()[0]


def _association_rows(conn, collection, fid):
    """Read one collection's stored associations through the internal helper."""
    if collection == "surface":
        sql = (
            "select property, target_collection, target_id::text "
            "from topology._surface_associations(%s::uuid) "
            "order by property, target_id"
        )
    elif collection == "surface2":
        sql = (
            "select property, target_collection, target_id::text "
            "from topology._surface2_associations(%s::uuid) "
            "order by property, target_id"
        )
    else:
        raise AssertionError(
            f"unexpected collection for association helper: {collection}"
        )
    return conn.execute(sql, (fid,)).fetchall()


def _sources_using_rows(conn, target_collection, ids):
    """Read reverse users of one or more target ids through the internal helper."""
    return conn.execute(
        "select collection, id::text, property, target_id::text "
        "from topology._sources_using(%s, %s::uuid[]) "
        "order by collection, id, property, target_id",
        (target_collection, ids),
    ).fetchall()


def _properties(conn, collection, fid):
    """Convenience wrapper for a feature's properties object."""
    return _item(conn, collection, fid)["properties"]


def _assert_rejected(report):
    assert report["committed"] is False
    assert report["items"][0]["sqlstate"] == "P0001"


def _assert_structure_failure(report, expected_findings):
    assert report == {
        "committed": False,
        "phase": "structure",
        "reason": None,
        "items": [],
        "structure": list(expected_findings),
        "geometry": [],
    }


def _assert_structure_clean_commit(report, expected_item_count):
    assert report["committed"] is True
    assert report["phase"] == "items"
    assert report["reason"] is None
    assert len(report["items"]) == expected_item_count
    assert report["structure"] == []
    assert report["geometry"] == []


def _case_delete_linked_target_rolls_back_with_full_finding():
    border_id = _new_id()
    surface_id = _new_id()
    return StructuralFailureCase(
        (
            _insert(
                "border1",
                _LINE_GEOM_ALT,
                {"identifikasjon": {"lokalid": border_id}},
                fid=border_id,
            ),
            _insert(
                "surface",
                _POLYGON_GEOM,
                {"boundedByOuter": [{"featuretype": "border1", "lokalid": border_id}]},
                fid=surface_id,
            ),
        ),
        (_delete("border1", border_id),),
        (
            {
                "reason": "missing_member",
                "source_collection": "surface",
                "source_id": surface_id,
                "property": "boundedByOuter",
                "target_collection": "border1",
                "target_id": border_id,
                "deleted_by_item": 0,
            },
        ),
        (("border1", border_id), ("surface", surface_id)),
    )


def _case_delete_target_reports_every_source_using_it():
    border_id = _new_id()
    surface_id = _new_id()
    surface2_id = _new_id()
    return StructuralFailureCase(
        (
            _insert(
                "border1",
                _LINE_GEOM_ALT_2,
                {"identifikasjon": {"lokalid": border_id}},
                fid=border_id,
            ),
            _insert(
                "surface",
                _POLYGON_GEOM,
                {"boundedByOuter": [{"featuretype": "border1", "lokalid": border_id}]},
                fid=surface_id,
            ),
            _insert(
                "surface2",
                _POLYGON_GEOM,
                {"boundedByOuter": [{"featuretype": "border1", "lokalid": border_id}]},
                fid=surface2_id,
            ),
        ),
        (_delete("border1", border_id),),
        (
            {
                "reason": "missing_member",
                "source_collection": "surface",
                "source_id": surface_id,
                "property": "boundedByOuter",
                "target_collection": "border1",
                "target_id": border_id,
                "deleted_by_item": 0,
            },
            {
                "reason": "missing_member",
                "source_collection": "surface2",
                "source_id": surface2_id,
                "property": "boundedByOuter",
                "target_collection": "border1",
                "target_id": border_id,
                "deleted_by_item": 0,
            },
        ),
        (("border1", border_id), ("surface", surface_id), ("surface2", surface2_id)),
    )


def _case_delete_two_targets_collects_findings_across_ids_and_collections():
    border1_id = _new_id()
    border3_id = _new_id()
    surface_id = _new_id()
    return StructuralFailureCase(
        (
            _insert(
                "border1",
                _LINE_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert("border3", _LINE_GEOM_ALT, {}, fid=border3_id),
            _insert(
                "surface",
                _POLYGON_GEOM,
                {
                    "boundedByOuter": [
                        {"featuretype": "border1", "lokalid": border1_id}
                    ],
                    "describedByNote": [{"featuretype": "border3", "id": border3_id}],
                },
                fid=surface_id,
            ),
        ),
        (_delete("border1", border1_id), _delete("border3", border3_id)),
        (
            {
                "reason": "missing_member",
                "source_collection": "surface",
                "source_id": surface_id,
                "property": "boundedByOuter",
                "target_collection": "border1",
                "target_id": border1_id,
                "deleted_by_item": 0,
            },
            {
                "reason": "missing_member",
                "source_collection": "surface",
                "source_id": surface_id,
                "property": "describedByNote",
                "target_collection": "border3",
                "target_id": border3_id,
                "deleted_by_item": 1,
            },
        ),
        (("border1", border1_id), ("border3", border3_id), ("surface", surface_id)),
    )


def _case_delete_non_footprint_link_still_reports_missing_member():
    border_id = _new_id()
    surface_id = _new_id()
    return StructuralFailureCase(
        (
            _insert("border3", _LINE_GEOM_ALT_2, {}, fid=border_id),
            _insert(
                "surface",
                _POLYGON_GEOM,
                {"describedByNote": [{"featuretype": "border3", "id": border_id}]},
                fid=surface_id,
            ),
        ),
        (_delete("border3", border_id),),
        (
            {
                "reason": "missing_member",
                "source_collection": "surface",
                "source_id": surface_id,
                "property": "describedByNote",
                "target_collection": "border3",
                "target_id": border_id,
                "deleted_by_item": 0,
            },
        ),
        (("border3", border_id), ("surface", surface_id)),
    )


def _case_delete_unlinked_target_commits_cleanly():
    border_id = _new_id()
    return StructuralSuccessCase(
        (
            _insert(
                "border1",
                _LINE_GEOM,
                {"identifikasjon": {"lokalid": border_id}},
                fid=border_id,
            ),
        ),
        (_delete("border1", border_id),),
    )


def _case_delete_source_removes_its_own_links_before_structural_checks():
    border_id = _new_id()
    surface_id = _new_id()
    return StructuralSuccessCase(
        (
            _insert(
                "border1",
                _LINE_GEOM_ALT,
                {"identifikasjon": {"lokalid": border_id}},
                fid=border_id,
            ),
            _insert(
                "surface",
                _POLYGON_GEOM,
                {"boundedByOuter": [{"featuretype": "border1", "lokalid": border_id}]},
                fid=surface_id,
            ),
        ),
        (_delete("surface", surface_id),),
        (("surface", surface_id),),
    )


def _case_transaction_with_no_deletes_keeps_structure_empty():
    return StructuralSuccessCase(
        (),
        (_insert("surface", _POLYGON_GEOM, {}, fid=_new_id()),),
    )


STRUCTURAL_FAILURE_CASE_BUILDERS = [
    pytest.param(
        _case_delete_linked_target_rolls_back_with_full_finding,
        id="delete-linked-target-rolls-back-with-full-finding",
    ),
    pytest.param(
        _case_delete_target_reports_every_source_using_it,
        id="delete-target-reports-every-source-using-it",
    ),
    pytest.param(
        _case_delete_two_targets_collects_findings_across_ids_and_collections,
        id="delete-two-targets-collects-findings-across-ids-and-collections",
    ),
    pytest.param(
        _case_delete_non_footprint_link_still_reports_missing_member,
        id="delete-non-footprint-link-still-reports-missing-member",
    ),
]


STRUCTURAL_SUCCESS_CASE_BUILDERS = [
    pytest.param(
        _case_delete_unlinked_target_commits_cleanly,
        id="delete-unlinked-target-commits-cleanly",
    ),
    pytest.param(
        _case_delete_source_removes_its_own_links_before_structural_checks,
        id="delete-source-removes-its-own-links-before-structural-checks",
    ),
    pytest.param(
        _case_transaction_with_no_deletes_keeps_structure_empty,
        id="transaction-with-no-deletes-keeps-structure-empty",
    ),
]


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

    The generated UUID is valid but no border1 row holds it.
    The item fails and no rows are written.
    """
    missing_id = _new_id()
    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [{"featuretype": "border1", "lokalid": missing_id}],
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


def test_create_with_two_links_reads_same_shape(topology_conn, borders):
    """Create with links reads back the same property shape the write accepted."""
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
    got = _properties(topology_conn, "surface", report["items"][0]["id"])
    assert got["boundedByOuter"] == [
        {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]},
        {"featuretype": "border1", "lokalid": borders["b1b_lokalid"]},
    ]


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
    got = _properties(topology_conn, "surface", report["items"][0]["id"])
    assert got["describedByNote"] == [
        {"featuretype": "border3", "id": borders["b3_id"]}
    ]


def test_read_uses_declared_identifier_keys(topology_conn, borders):
    """Each link element uses the identifier key declared by its target collection."""
    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]}
                ],
                "describedByNote": [{"featuretype": "border3", "id": borders["b3_id"]}],
            },
        ),
    )

    got = _properties(topology_conn, "surface", report["items"][0]["id"])
    assert got["boundedByOuter"] == [
        {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]}
    ]
    assert got["describedByNote"] == [
        {"featuretype": "border3", "id": borders["b3_id"]}
    ]


def test_read_uses_declared_featuretype(topology_conn, borders):
    """Each read-back link carries the target collection declared in the catalogue."""
    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByShared": [
                    {"featuretype": "border2", "lokalid": borders["b2_lokalid"]}
                ]
            },
        ),
    )

    got = _properties(topology_conn, "surface", report["items"][0]["id"])
    assert got["boundedByShared"] == [
        {"featuretype": "border2", "lokalid": borders["b2_lokalid"]}
    ]


def test_property_with_no_links_is_absent_on_read(topology_conn):
    """A declared property with no links is omitted rather than returned as []."""
    report = _txn(topology_conn, _insert("surface", _POLYGON_GEOM, {}))

    got = _properties(topology_conn, "surface", report["items"][0]["id"])
    assert "boundedByOuter" not in got
    assert "boundedByShared" not in got
    assert "describedByNote" not in got


def test_update_leaves_unnamed_properties_intact(topology_conn, borders):
    """PATCH: a property absent from the document keeps its existing rows.

    Surface starts with rows under both boundedByOuter and boundedByShared.
    An update that only names boundedByShared must leave boundedByOuter untouched.
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

    got = _properties(topology_conn, "surface", surface_id)
    assert got["boundedByOuter"] == [
        {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]}
    ]
    assert "boundedByShared" not in got


def test_replace_clears_declared_properties_not_in_document(topology_conn, borders):
    """PUT: declared properties absent from the replace document are cleared.

    Surface starts with a boundedByOuter row. A replace that only names
    boundedByShared must clear boundedByOuter's rows entirely.
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

    got = _properties(topology_conn, "surface", surface_id)
    assert "boundedByOuter" not in got
    assert got["boundedByShared"] == [
        {"featuretype": "border2", "lokalid": borders["b2_lokalid"]}
    ]


def test_empty_array_clears_that_property(topology_conn, borders):
    """An empty array in the document clears that property's rows.

    An absent key (PATCH) means 'leave alone'; an empty array means 'remove all'.
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

    got = _properties(topology_conn, "surface", surface_id)
    assert "boundedByOuter" not in got


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

    assert _item(topology_conn, "surface", surface_id) is None


def test_delete_target_leaves_inbound_rows_intact(topology_conn, borders):
    """Deleting a target feature does not remove inbound association rows.

    There is no FK on target_id by design: a dangling reference must remain
    reportable by structural checks. This test verifies no cascade was added.
    """
    disposable_lokalid = _new_id()
    disposable_report = _txn(
        topology_conn,
        _insert(
            "border1", _LINE_GEOM, {"identifikasjon": {"lokalid": disposable_lokalid}}
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
                    {"featuretype": "border1", "lokalid": disposable_lokalid}
                ],
            },
        ),
    )
    surface_id = create_report["items"][0]["id"]

    _txn(topology_conn, _delete("border1", disposable_id))

    got = _properties(topology_conn, "surface", surface_id)
    assert got["boundedByOuter"] == [
        {"featuretype": "border1", "lokalid": disposable_lokalid}
    ]


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
    got = _properties(topology_conn, "surface", report["items"][0]["id"])
    assert got["boundedByOuter"] == [
        {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]}
    ]


def test_write_read_replace_roundtrip_keeps_links(topology_conn, borders):
    """A feature read back through feature_item round-trips through replace unchanged."""
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
                "describedByNote": [{"featuretype": "border3", "id": borders["b3_id"]}],
            },
        ),
    )
    surface_id = report["items"][0]["id"]
    before = _item(topology_conn, "surface", surface_id)

    replaced = _txn(
        topology_conn,
        {
            "action": "replace",
            "collection": "surface",
            "id": surface_id,
            "feature": {
                "type": "Feature",
                "geometry": before["geometry"],
                "properties": before["properties"],
            },
        },
    )

    assert replaced["committed"] is True
    after = _item(topology_conn, "surface", surface_id)
    assert after["id"] == before["id"]
    assert after["geometry"] == before["geometry"]
    assert (
        after["properties"]["boundedByOuter"] == before["properties"]["boundedByOuter"]
    )
    assert (
        after["properties"]["describedByNote"]
        == before["properties"]["describedByNote"]
    )
    assert after["properties"]["created_at"] == before["properties"]["created_at"]
    assert after["properties"]["updated_at"] != before["properties"]["updated_at"]


def test_link_order_is_stable_across_reads(topology_conn, borders):
    """Repeated reads return link arrays in a stable order."""
    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": borders["b1b_lokalid"]},
                    {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]},
                ]
            },
        ),
    )
    surface_id = report["items"][0]["id"]

    first = _properties(topology_conn, "surface", surface_id)["boundedByOuter"]
    second = _properties(topology_conn, "surface", surface_id)["boundedByOuter"]
    assert first == second


def test_feature_items_returns_links_for_multiple_features(topology_conn, borders):
    """feature_items returns link properties for several features in one collection."""
    first = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]}
                ]
            },
        ),
    )
    second = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {"describedByNote": [{"featuretype": "border3", "id": borders["b3_id"]}]},
        ),
    )

    features = _items(topology_conn, "surface")["features"]
    by_id = {str(feature["id"]): feature for feature in features}
    assert by_id[first["items"][0]["id"]]["properties"]["boundedByOuter"] == [
        {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]}
    ]
    assert by_id[second["items"][0]["id"]]["properties"]["describedByNote"] == [
        {"featuretype": "border3", "id": borders["b3_id"]}
    ]


def test_collection_with_no_declared_link_properties_reads_as_before(topology_conn):
    """A collection with no declared relationships reads without any link properties."""
    report = _txn(topology_conn, _insert("border3", _LINE_GEOM, {}))

    got = _properties(topology_conn, "border3", report["items"][0]["id"])
    assert set(got) == {"created_at", "updated_at"}


def test_associations_returns_one_row_per_link_including_dangling(
    topology_conn, borders
):
    """The internal associations helper returns stored rows even after target deletion."""
    disposable_lokalid = _new_id()
    disposable = _txn(
        topology_conn,
        _insert(
            "border1", _LINE_GEOM, {"identifikasjon": {"lokalid": disposable_lokalid}}
        ),
    )
    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]},
                    {"featuretype": "border1", "lokalid": disposable_lokalid},
                ]
            },
        ),
    )
    surface_id = report["items"][0]["id"]

    _txn(topology_conn, _delete("border1", disposable["items"][0]["id"]))

    expected_rows = sorted(
        [
            ("boundedByOuter", "border1", borders["b1a_lokalid"]),
            ("boundedByOuter", "border1", disposable_lokalid),
        ],
        key=lambda row: row[2],
    )
    assert _association_rows(topology_conn, "surface", surface_id) == expected_rows


def test_sources_using_is_polymorphic_on_source_collection(topology_conn, borders):
    """One target can be referenced from more than one source collection."""
    reverse_id = str(uuid.uuid4())
    report = _txn(
        topology_conn,
        _insert(
            "border1",
            _LINE_GEOM_ALT,
            {"identifikasjon": {"lokalid": reverse_id}},
        ),
        _insert(
            "surface",
            _POLYGON_GEOM,
            {"boundedByOuter": [{"featuretype": "border1", "lokalid": reverse_id}]},
        ),
        _insert(
            "surface2",
            _POLYGON_GEOM,
            {"boundedByOuter": [{"featuretype": "border1", "lokalid": reverse_id}]},
        ),
    )
    surface_id = report["items"][1]["id"]
    surface2_id = report["items"][2]["id"]

    assert _sources_using_rows(topology_conn, "border1", [reverse_id]) == [
        ("surface", surface_id, "boundedByOuter", reverse_id),
        ("surface2", surface2_id, "boundedByOuter", reverse_id),
    ]


def test_sources_using_accepts_many_ids_in_one_call(topology_conn, borders):
    """Reverse lookup accepts several target ids in one set-based call."""
    reverse_a = str(uuid.uuid4())
    reverse_b = str(uuid.uuid4())
    report = _txn(
        topology_conn,
        _insert(
            "border1",
            _LINE_GEOM_ALT,
            {"identifikasjon": {"lokalid": reverse_a}},
        ),
        _insert(
            "border1",
            _LINE_GEOM_ALT_2,
            {"identifikasjon": {"lokalid": reverse_b}},
        ),
        _insert(
            "surface",
            _POLYGON_GEOM,
            {"boundedByOuter": [{"featuretype": "border1", "lokalid": reverse_a}]},
        ),
        _insert(
            "surface2",
            _POLYGON_GEOM,
            {"boundedByOuter": [{"featuretype": "border1", "lokalid": reverse_b}]},
        ),
    )
    first_id = report["items"][2]["id"]
    second_id = report["items"][3]["id"]

    assert _sources_using_rows(
        topology_conn,
        "border1",
        [reverse_a, reverse_b],
    ) == [
        ("surface", first_id, "boundedByOuter", reverse_a),
        ("surface2", second_id, "boundedByOuter", reverse_b),
    ]


@pytest.mark.parametrize("case_builder", STRUCTURAL_FAILURE_CASE_BUILDERS)
def test_structural_checks_missing_member_failures_roll_back_with_findings(
    topology_conn, case_builder
):
    case = case_builder()
    setup = _txn(topology_conn, *case.setup_items)
    _assert_structure_clean_commit(setup, len(case.setup_items))

    report = _txn(topology_conn, *case.tx_items)

    _assert_structure_failure(report, case.expected_findings)
    for collection, fid in case.expected_present:
        assert _item(topology_conn, collection, fid) is not None


@pytest.mark.parametrize("case_builder", STRUCTURAL_SUCCESS_CASE_BUILDERS)
def test_structural_checks_clean_documents_commit_without_structure_findings(
    topology_conn, case_builder
):
    case = case_builder()
    if case.setup_items:
        setup = _txn(topology_conn, *case.setup_items)
        _assert_structure_clean_commit(setup, len(case.setup_items))

    report = _txn(topology_conn, *case.tx_items)

    _assert_structure_clean_commit(report, len(case.tx_items))
    for collection, fid in case.expected_association_clears:
        assert _association_rows(topology_conn, collection, fid) == []


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
