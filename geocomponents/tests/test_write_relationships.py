"""Contract tests for association links on the transaction and read paths."""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from copy import deepcopy
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

# Geometry fixtures for the topology tests (all SRID 4326, 2D).
_LINE_GEOM = {"type": "LineString", "coordinates": [[0, 0], [20, 0], [20, 20]]}
_LINE_GEOM_ALT = {
    "type": "LineString",
    "coordinates": [[20, 20], [0, 20], [0, 0]],
}
_LINE_GEOM_ALT_2 = {
    "type": "LineString",
    "coordinates": [[30, 0], [40, 0], [40, 10], [30, 10], [30, 0]],
}
_LINE_GEOM_WIDER = {
    "type": "LineString",
    "coordinates": [[0, 0], [25, 0], [20, 20]],
}
_NOTE_LINE_GEOM = {"type": "LineString", "coordinates": [[50, 0], [51, 0]]}
_OUTER_RING_GEOM = {
    "type": "LineString",
    "coordinates": [[0, 0], [20, 0], [20, 20], [0, 20], [0, 0]],
}
_INNER_RING_GEOM = {
    "type": "LineString",
    "coordinates": [[5, 5], [15, 5], [15, 15], [5, 15], [5, 5]],
}
_CROSSING_LINE_GEOM = {"type": "LineString", "coordinates": [[0, 0], [20, 20]]}
_CROSSING_LINE_GEOM_ALT = {
    "type": "LineString",
    "coordinates": [[20, 0], [0, 20]],
}
_OPEN_LINE_GEOM = {"type": "LineString", "coordinates": [[0, 0], [20, 0]]}
_OPEN_LINE_GEOM_ALT = {
    "type": "LineString",
    "coordinates": [[20, 0.001], [20, 20]],
}
_OPEN_SHARED_LINE_GEOM = {
    "type": "LineString",
    "coordinates": [[0, 0], [25, 0], [25, 20]],
}
_FREE_FLOATING_LINE_GEOM = {
    "type": "LineString",
    "coordinates": [[30, 0], [40, 0]],
}
_THREE_WAY_OUTER_GEOM = {"type": "LineString", "coordinates": [[0, 0], [20, 0]]}
_THREE_WAY_SHARED_GEOM = {
    "type": "LineString",
    "coordinates": [[20, 0], [20, 20], [0, 20]],
}
_THREE_WAY_CONDITIONAL_GEOM = {
    "type": "LineString",
    "coordinates": [[0, 20], [0, 0]],
}
_POLYGON_GEOM = {
    "type": "MultiPolygon",
    "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]],
}
_RING_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [20, 0], [20, 20], [0, 20], [0, 0]]],
}
_WIDER_RING_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [25, 0], [20, 20], [0, 20], [0, 0]]],
}
_TWO_RINGS_MULTIPOLYGON = {
    "type": "MultiPolygon",
    "coordinates": [
        [[[0, 0], [20, 0], [20, 20], [0, 20], [0, 0]]],
        [[[30, 0], [40, 0], [40, 10], [30, 10], [30, 0]]],
    ],
}
_DERIVED_COLLECTIONS = {"surface", "surface2"}


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


@dataclass(frozen=True)
class FootprintRuleFailureCase:
    raw: dict
    setup_items: tuple[dict, ...]
    tx_items: tuple[dict, ...]
    expected_findings: tuple[dict, ...]
    expected_present: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class FootprintRuleSuccessCase:
    raw: dict
    setup_items: tuple[dict, ...]
    tx_items: tuple[dict, ...]


@dataclass(frozen=True)
class BoundsFailureCase:
    raw: dict
    setup_items: tuple[dict, ...]
    tx_items: tuple[dict, ...]
    expected_findings: tuple[dict, ...]
    expected_present: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class BoundsSuccessCase:
    raw: dict
    setup_items: tuple[dict, ...]
    tx_items: tuple[dict, ...]


@dataclass(frozen=True)
class FootprintGeometryFailureCase:
    raw: dict
    setup_items: tuple[dict, ...]
    tx_items: tuple[dict, ...]
    expected_findings: tuple[dict, ...]
    expected_absent: tuple[tuple[str, str], ...] = ()
    expected_present: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class FootprintGeometrySuccessCase:
    raw: dict
    setup_items: tuple[dict, ...]
    tx_items: tuple[dict, ...]


# --------------------------------------------------------------------------
# Fixture: topology schema with tables + functions
# --------------------------------------------------------------------------


def _load_plan():
    return _load_plan_from_raw(_topology_fixture_raw_without_bounds())


def _topology_fixture_raw() -> dict:
    return yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))


def _topology_fixture_raw_without_bounds() -> dict:
    raw = _topology_fixture_raw()
    for coll in raw["collections"]:
        coll.pop("bounds", None)
    return raw


def _load_plan_from_raw(raw: dict):
    return build_schema_plan(resolve_dataset(DatasetDef.model_validate(raw), Commons()))


@contextmanager
def _topology_case_conn(db: str, raw: dict):
    with _schema_conn(db, _load_plan_from_raw(raw)) as conn:
        yield conn


def _case_raw() -> dict:
    raw = _bounds_case_raw()
    for coll in raw["collections"]:
        coll.pop("bounds", None)
    return raw


def _bounds_case_raw() -> dict:
    raw = deepcopy(_topology_fixture_raw())
    raw["name"] = f"topology_case_{uuid.uuid4().hex[:8]}"
    return raw


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
      b4_id        uuid of border4        (wire key: 'id')
      b3_id        uuid of border3        (wire key: 'id' — no outward identifier)
    """
    b1a_id, b1b_id = sorted([_new_id(), _new_id()])
    b2_id = _new_id()
    b4_id = _new_id()
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
        _insert("border2", _LINE_GEOM_ALT, {"identifikasjon": {"lokalid": b2_id}}),
    )
    _txn(
        topology_conn,
        _insert("border4", _OUTER_RING_GEOM, {"is_bounding": True}, fid=b4_id),
    )
    b3 = _txn(topology_conn, _insert("border3", _NOTE_LINE_GEOM, {}))
    return {
        "b1a_lokalid": b1a_id,
        "b1b_lokalid": b1b_id,
        "b2_lokalid": b2_id,
        "b4_id": b4_id,
        "b3_id": b3["items"][0]["id"],
    }


# --------------------------------------------------------------------------
# Transaction helpers
# --------------------------------------------------------------------------


def _txn(conn, *items, dataset="topology"):
    """Run ogc.transaction('topology', ...) and return the JSON report."""
    doc = {"semantic": "atomic", "transaction": list(items)}
    return conn.execute(
        "select ogc.transaction(%s, %s::jsonb)",
        (dataset, json.dumps(doc)),
    ).fetchone()[0]


def _txn_doc(conn, document, *, dataset="topology"):
    return conn.execute(
        "select ogc.transaction(%s, %s::jsonb)",
        (dataset, json.dumps(document)),
    ).fetchone()[0]


def _insert(collection, geom, props, *, fid=None, keep_geometry=False):
    feature = {"type": "Feature", "properties": props}
    if keep_geometry or collection not in _DERIVED_COLLECTIONS:
        feature["geometry"] = geom
    if fid is not None:
        feature["id"] = fid
    return {
        "action": "insert",
        "collection": collection,
        "feature": feature,
    }


def _insert_without_geometry(collection, props, *, fid=None):
    feature = {"type": "Feature", "properties": props}
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


def _update_with_geometry(collection, fid, geom, props):
    return {
        "action": "update",
        "collection": collection,
        "id": fid,
        "feature": {"type": "Feature", "geometry": geom, "properties": props},
    }


def _replace(collection, fid, geom, props, *, keep_geometry=False):
    """PUT: full document, all columns and link properties replaced."""
    feature = {"type": "Feature", "properties": props}
    if keep_geometry or collection not in _DERIVED_COLLECTIONS:
        feature["geometry"] = geom
    return {
        "action": "replace",
        "collection": collection,
        "id": fid,
        "feature": feature,
    }


def _delete(collection, fid):
    return {"action": "delete", "collection": collection, "id": fid}


def _item(conn, collection, fid, *, dataset="topology"):
    """Read one feature through the public OGC function."""
    return conn.execute(
        "select ogc.feature_item(%s, %s, %s::uuid)",
        (dataset, collection, fid),
    ).fetchone()[0]


def _items(conn, collection, lim=1000, *, dataset="topology"):
    """Read a feature collection through the public OGC function."""
    return conn.execute(
        "select ogc.feature_items(%s, %s, %s, %s, %s, %s)",
        (dataset, collection, None, lim, 0, True),
    ).fetchone()[0]


def _association_rows(conn, collection, fid, *, dataset="topology"):
    """Read one collection's stored associations through the internal helper."""
    if collection == "surface":
        sql = f"select property, target_collection, target_id::text from {dataset}._surface_associations(%s::uuid) order by property, target_id"  # noqa: S608
    elif collection == "surface2":
        sql = f"select property, target_collection, target_id::text from {dataset}._surface2_associations(%s::uuid) order by property, target_id"  # noqa: S608
    else:
        raise AssertionError(
            f"unexpected collection for association helper: {collection}"
        )
    return conn.execute(sql, (fid,)).fetchall()


def _sources_using_rows(conn, target_collection, ids, *, dataset="topology"):
    """Read reverse users of one or more target ids through the internal helper."""
    sql = f"select collection, id::text, property, target_id::text from {dataset}._sources_using(%s, %s::uuid[]) order by collection, id, property, target_id"  # noqa: S608
    return conn.execute(
        sql,
        (target_collection, ids),
    ).fetchall()


def _footprint_members_rows(conn, collection, fid, *, dataset="topology"):
    sql = psycopg.sql.SQL(
        "select property, target_collection, target_id::text, included, ST_AsText(geom) "
        "from {}.{}(%s::uuid) order by property, target_id"
    ).format(
        psycopg.sql.Identifier(dataset),
        psycopg.sql.Identifier(f"_{collection}_footprint_members"),
    )
    return conn.execute(sql, (fid,)).fetchall()


def _stored_geometry_equals(
    conn, collection, fid, expected_geometry, *, dataset="topology"
):
    sql = psycopg.sql.SQL(
        'select ST_Equals("geometry", ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)) '
        'from {}.{} where "id" = %s::uuid'
    ).format(
        psycopg.sql.Identifier(dataset),
        psycopg.sql.Identifier(collection),
    )
    return conn.execute(sql, (json.dumps(expected_geometry), fid)).fetchone()[0]


def _stored_geometry_meta(conn, collection, fid, *, dataset="topology"):
    sql = psycopg.sql.SQL(
        'select ST_AsGeoJSON("geometry")::jsonb, GeometryType("geometry"), '
        'ST_NumGeometries("geometry") from {}.{} where "id" = %s::uuid'
    ).format(
        psycopg.sql.Identifier(dataset),
        psycopg.sql.Identifier(collection),
    )
    return conn.execute(sql, (fid,)).fetchone()


def _properties(conn, collection, fid):
    """Convenience wrapper for a feature's properties object."""
    return _item(conn, collection, fid)["properties"]


def _assert_rejected(report):
    assert report["committed"] is False
    assert report["sqlstate"] is None
    assert report["items"][0]["sqlstate"] == "P0001"


def _assert_structure_failure(report, expected_findings):
    assert report == {
        "committed": False,
        "phase": "structure",
        "reason": None,
        "sqlstate": None,
        "items": [],
        "structure": list(expected_findings),
        "geometry": [],
    }


def _assert_geometry_failure(report, expected_findings):
    assert report == {
        "committed": False,
        "phase": "geometry",
        "reason": None,
        "sqlstate": None,
        "items": [],
        "structure": [],
        "geometry": list(expected_findings),
    }


def _assert_structure_clean_commit(report, expected_item_count):
    assert report["committed"] is True
    assert report["phase"] == "items"
    assert report["reason"] is None
    assert report["sqlstate"] is None
    assert len(report["items"]) == expected_item_count
    assert report["structure"] == []
    assert report["geometry"] == []


def _assert_raised_phase_failure(report, *, phase, sqlstate, reason_substring):
    assert report == {
        "committed": False,
        "phase": phase,
        "reason": report["reason"],
        "items": [],
        "sqlstate": sqlstate,
        "structure": [],
        "geometry": [],
    }
    assert reason_substring in report["reason"]


def _footprint_structure_finding(
    collection,
    fid,
    reason,
    *,
    counts,
    roles=(),
):
    members, included = counts
    details = {"roles": sorted(roles)} if roles else {}
    return {
        "valid": False,
        "collection": collection,
        "id": fid,
        "rule": "footprint",
        "reason": reason,
        "members": members,
        "included": included,
        "details": details,
    }


def _bounds_structure_finding(collection, fid, *, expected, actual, owners=()):
    return {
        "reason": "member_bounds_violated",
        "collection": collection,
        "id": fid,
        "expected": expected,
        "actual": actual,
        "owners": [
            {"collection": owner_collection, "id": owner_id}
            for owner_collection, owner_id in sorted(owners)
        ],
    }


def _footprint_geometry_finding(  # noqa: PLR0913
    collection,
    fid,
    reason,
    *,
    counts,
    areas=0,
    holes=0,
    unused=(),
):
    members, included = counts
    if unused:
        details = {
            "unused": [
                {"collection": target_collection, "id": target_id}
                for target_collection, target_id in unused
            ]
        }
    elif reason == "multiple_disjoint_areas":
        details = {"areas": areas}
    elif reason == "holes_not_allowed":
        details = {"holes": holes}
    else:
        details = {}
    return {
        "valid": False,
        "collection": collection,
        "id": fid,
        "rule": "footprint",
        "reason": reason,
        "members": members,
        "included": included,
        "areas": areas,
        "holes": holes,
        "details": details,
    }


def _border1_ref(lokalid: str) -> dict:
    return {"featuretype": "border1", "lokalid": lokalid}


def _border2_ref(lokalid: str) -> dict:
    return {"featuretype": "border2", "lokalid": lokalid}


def _border3_ref(fid: str) -> dict:
    return {"featuretype": "border3", "id": fid}


def _border4_ref(fid: str) -> dict:
    return {"featuretype": "border4", "id": fid}


def _surface_props(
    *,
    outer: tuple[str, ...] = (),
    shared: tuple[str, ...] = (),
    notes: tuple[str, ...] = (),
    conditional: tuple[str, ...] = (),
) -> dict:
    props = {}
    if outer:
        props["boundedByOuter"] = [_border1_ref(lokalid) for lokalid in outer]
    if shared:
        props["boundedByShared"] = [_border2_ref(lokalid) for lokalid in shared]
    if notes:
        props["describedByNote"] = [_border3_ref(fid) for fid in notes]
    if conditional:
        props["boundedByConditional"] = [_border4_ref(fid) for fid in conditional]
    return props


def _surface2_props(*outer_lokalids: str) -> dict:
    return {"boundedByOuter": [_border1_ref(lokalid) for lokalid in outer_lokalids]}


def _surface_case_with_three_way_alternative() -> dict:
    raw = _case_raw()
    surface = next(coll for coll in raw["collections"] if coll["name"] == "surface")
    surface["geometry"]["derived"]["one_of"] = [
        [
            "boundedByOuter",
            "boundedByShared",
            {"name": "boundedByConditional", "when": "is_bounding"},
        ]
    ]
    return raw


def _surface_case_with_described_by_note_target(target: str) -> dict:
    raw = _bounds_case_raw()
    surface = next(coll for coll in raw["collections"] if coll["name"] == "surface")
    for rel in surface["relationships"]:
        if rel["property"] == "describedByNote":
            rel["target"] = target
            break
    return raw


def _border1_segment_item(lokalid: str, geom: dict) -> dict:
    return _insert(
        "border1",
        geom,
        {"identifikasjon": {"lokalid": lokalid}},
        fid=lokalid,
    )


def _border1_ring_pair_items(first_id: str, second_id: str) -> tuple[dict, dict]:
    return (
        _border1_segment_item(first_id, _LINE_GEOM),
        _border1_segment_item(second_id, _LINE_GEOM_ALT),
    )


def _case_delete_linked_target_rolls_back_with_full_finding():
    border_id = _new_id()
    surface_id = _new_id()
    return StructuralFailureCase(
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
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
    border2_id = _new_id()
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
            _insert(
                "border2",
                _LINE_GEOM_ALT,
                {"identifikasjon": {"lokalid": border2_id}},
                fid=border2_id,
            ),
            _insert("border3", _NOTE_LINE_GEOM, {}, fid=border3_id),
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(
                    outer=(border1_id,),
                    shared=(border2_id,),
                    notes=(border3_id,),
                ),
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
    border1_id = _new_id()
    border2_id = _new_id()
    surface_id = _new_id()
    return StructuralFailureCase(
        (
            _insert(
                "border1",
                _LINE_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "border2",
                _LINE_GEOM_ALT,
                {"identifikasjon": {"lokalid": border2_id}},
                fid=border2_id,
            ),
            _insert("border3", _NOTE_LINE_GEOM, {}, fid=border_id),
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(
                    outer=(border1_id,),
                    shared=(border2_id,),
                    notes=(border_id,),
                ),
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
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": border_id}},
                fid=border_id,
            ),
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border_id,)),
                fid=surface_id,
            ),
        ),
        (_delete("surface", surface_id),),
        (("surface", surface_id),),
    )


def _case_transaction_with_no_deletes_keeps_structure_empty():
    return StructuralSuccessCase(
        (),
        (_insert_without_geometry("surface2", {}, fid=_new_id()),),
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


def _case_outer_and_shared_are_valid():
    raw = _case_raw()
    border1_id = _new_id()
    border2_id = _new_id()
    surface_id = _new_id()
    return FootprintRuleSuccessCase(
        raw,
        (
            _insert(
                "border1",
                _LINE_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "border2",
                _LINE_GEOM_ALT,
                {"identifikasjon": {"lokalid": border2_id}},
                fid=border2_id,
            ),
        ),
        (
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border1_id,), shared=(border2_id,)),
                fid=surface_id,
            ),
        ),
    )


def _case_outer_only_is_valid_subset():
    raw = _case_raw()
    border1_id = _new_id()
    surface_id = _new_id()
    return FootprintRuleSuccessCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
        ),
        (
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border1_id,)),
                fid=surface_id,
            ),
        ),
    )


def _case_outer_and_conditional_true_conflict():
    raw = _case_raw()
    border1_id = _new_id()
    border4_id = _new_id()
    surface_id = _new_id()
    return FootprintRuleFailureCase(
        raw,
        (
            _insert(
                "border1",
                _LINE_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert("border4", _LINE_GEOM_ALT, {"is_bounding": True}, fid=border4_id),
        ),
        (
            _insert(
                "surface",
                _POLYGON_GEOM,
                {
                    "boundedByOuter": [
                        {"featuretype": "border1", "lokalid": border1_id}
                    ],
                    "boundedByConditional": [
                        {"featuretype": "border4", "id": border4_id}
                    ],
                },
                fid=surface_id,
            ),
        ),
        (
            _footprint_structure_finding(
                "surface",
                surface_id,
                "conflicting_boundary_roles",
                counts=(2, 2),
                roles=("boundedByConditional", "boundedByOuter"),
            ),
        ),
        (("border1", border1_id), ("border4", border4_id)),
    )


def _case_outer_and_conditional_false_is_valid():
    raw = _case_raw()
    border1_id = _new_id()
    border4_id = _new_id()
    surface_id = _new_id()
    return FootprintRuleSuccessCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert("border4", _LINE_GEOM_ALT, {"is_bounding": False}, fid=border4_id),
        ),
        (
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border1_id,), conditional=(border4_id,)),
                fid=surface_id,
            ),
        ),
    )


def _case_conditional_only_true_is_valid_subset():
    raw = _case_raw()
    border4_id = _new_id()
    surface_id = _new_id()
    return FootprintRuleSuccessCase(
        raw,
        (_insert("border4", _OUTER_RING_GEOM, {"is_bounding": True}, fid=border4_id),),
        (
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(conditional=(border4_id,)),
                fid=surface_id,
            ),
        ),
    )


def _case_conditional_only_false_is_no_boundary():
    raw = _case_raw()
    border4_id = _new_id()
    surface_id = _new_id()
    return FootprintRuleFailureCase(
        raw,
        (_insert("border4", _LINE_GEOM_ALT, {"is_bounding": False}, fid=border4_id),),
        (
            _insert(
                "surface",
                _POLYGON_GEOM,
                {
                    "boundedByConditional": [
                        {"featuretype": "border4", "id": border4_id}
                    ]
                },
                fid=surface_id,
            ),
        ),
        (
            _footprint_structure_finding(
                "surface", surface_id, "no_boundary", counts=(1, 0)
            ),
        ),
        (("border4", border4_id),),
    )


def _case_optional_surface_with_no_links_is_valid():
    raw = _case_raw()
    surface_id = _new_id()
    return FootprintRuleSuccessCase(
        raw,
        (),
        (_insert_without_geometry("surface2", {}, fid=surface_id),),
    )


def _case_described_by_note_only_is_no_boundary():
    raw = _case_raw()
    border3_id = _new_id()
    surface_id = _new_id()
    return FootprintRuleFailureCase(
        raw,
        (_insert("border3", _NOTE_LINE_GEOM, {}, fid=border3_id),),
        (
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(notes=(border3_id,)),
                fid=surface_id,
            ),
        ),
        (
            _footprint_structure_finding(
                "surface", surface_id, "no_boundary", counts=(0, 0)
            ),
        ),
        (("border3", border3_id),),
    )


def _case_touching_when_target_rechecks_surface():
    raw = _case_raw()
    border1_id = _new_id()
    border4_id = _new_id()
    surface_id = _new_id()
    return FootprintRuleFailureCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert("border4", _LINE_GEOM_ALT, {"is_bounding": False}, fid=border4_id),
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border1_id,), conditional=(border4_id,)),
                fid=surface_id,
            ),
        ),
        (_update("border4", border4_id, {"is_bounding": True}),),
        (
            _footprint_structure_finding(
                "surface",
                surface_id,
                "conflicting_boundary_roles",
                counts=(2, 2),
                roles=("boundedByConditional", "boundedByOuter"),
            ),
        ),
        (("border1", border1_id), ("border4", border4_id), ("surface", surface_id)),
    )


def _case_two_surfaces_both_conflict_are_both_reported():
    raw = _case_raw()
    border1_id = _new_id()
    border4_id = _new_id()
    surface_a_id, surface_b_id = sorted([_new_id(), _new_id()])
    return FootprintRuleFailureCase(
        raw,
        (
            _insert(
                "border1",
                _LINE_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert("border4", _LINE_GEOM_ALT, {"is_bounding": True}, fid=border4_id),
        ),
        (
            _insert(
                "surface",
                _POLYGON_GEOM,
                {
                    "boundedByOuter": [
                        {"featuretype": "border1", "lokalid": border1_id}
                    ],
                    "boundedByConditional": [
                        {"featuretype": "border4", "id": border4_id}
                    ],
                },
                fid=surface_a_id,
            ),
            _insert(
                "surface",
                _POLYGON_GEOM,
                {
                    "boundedByOuter": [
                        {"featuretype": "border1", "lokalid": border1_id}
                    ],
                    "boundedByConditional": [
                        {"featuretype": "border4", "id": border4_id}
                    ],
                },
                fid=surface_b_id,
            ),
        ),
        (
            _footprint_structure_finding(
                "surface",
                surface_a_id,
                "conflicting_boundary_roles",
                counts=(2, 2),
                roles=("boundedByConditional", "boundedByOuter"),
            ),
            _footprint_structure_finding(
                "surface",
                surface_b_id,
                "conflicting_boundary_roles",
                counts=(2, 2),
                roles=("boundedByConditional", "boundedByOuter"),
            ),
        ),
        (("border1", border1_id), ("border4", border4_id)),
    )


FOOTPRINT_RULE_FAILURE_CASE_BUILDERS = [
    pytest.param(
        _case_outer_and_conditional_true_conflict,
        id="outer-and-conditional-true-conflict",
    ),
    pytest.param(
        _case_conditional_only_false_is_no_boundary,
        id="conditional-only-false-no-boundary",
    ),
    pytest.param(
        _case_described_by_note_only_is_no_boundary,
        id="described-by-note-only-no-boundary",
    ),
    pytest.param(
        _case_touching_when_target_rechecks_surface,
        id="touching-when-target-rechecks-surface",
    ),
    pytest.param(
        _case_two_surfaces_both_conflict_are_both_reported,
        id="two-surfaces-both-conflict-reported",
    ),
]


FOOTPRINT_RULE_SUCCESS_CASE_BUILDERS = [
    pytest.param(_case_outer_and_shared_are_valid, id="outer-and-shared-valid"),
    pytest.param(_case_outer_only_is_valid_subset, id="outer-only-valid-subset"),
    pytest.param(
        _case_outer_and_conditional_false_is_valid,
        id="outer-and-conditional-false-valid",
    ),
    pytest.param(
        _case_conditional_only_true_is_valid_subset,
        id="conditional-only-true-valid-subset",
    ),
    pytest.param(
        _case_optional_surface_with_no_links_is_valid,
        id="optional-surface-no-links-valid",
    ),
]


def _case_bounds_one_curve_claimed_by_two_surfaces():
    raw = _bounds_case_raw()
    border1_id = _new_id()
    surface_id = _new_id()
    surface2_id = _new_id()
    return BoundsFailureCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border1_id,)),
                fid=surface_id,
            ),
        ),
        (
            _insert(
                "surface2",
                _POLYGON_GEOM,
                _surface2_props(border1_id),
                fid=surface2_id,
            ),
        ),
        (
            _bounds_structure_finding(
                "border1",
                border1_id,
                expected=1,
                actual=2,
                owners=(("surface", surface_id), ("surface2", surface2_id)),
            ),
        ),
        (("border1", border1_id), ("surface", surface_id)),
    )


def _case_bounds_orphan_curve_inserted_without_link():
    raw = _bounds_case_raw()
    border1_id = _new_id()
    return BoundsFailureCase(
        raw,
        (),
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
        ),
        (_bounds_structure_finding("border1", border1_id, expected=1, actual=0),),
    )


def _case_bounds_two_owner_divider_with_one_surface_fails():
    raw = _bounds_case_raw()
    border1_id = _new_id()
    border2_id = _new_id()
    surface_id = _new_id()
    return BoundsFailureCase(
        raw,
        (),
        (
            _insert(
                "border1",
                _LINE_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "border2",
                _LINE_GEOM_ALT,
                {"identifikasjon": {"lokalid": border2_id}},
                fid=border2_id,
            ),
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border1_id,), shared=(border2_id,)),
                fid=surface_id,
            ),
        ),
        (
            _bounds_structure_finding(
                "border2",
                border2_id,
                expected=2,
                actual=1,
                owners=(("surface", surface_id),),
            ),
        ),
    )


def _case_bounds_surface_update_to_empty_counts_ex_target():
    raw = _bounds_case_raw()
    border1_id = _new_id()
    surface2_id = _new_id()
    return BoundsFailureCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "surface2",
                _POLYGON_GEOM,
                _surface2_props(border1_id),
                fid=surface2_id,
            ),
        ),
        (_update("surface2", surface2_id, {"boundedByOuter": []}),),
        (_bounds_structure_finding("border1", border1_id, expected=1, actual=0),),
        (("border1", border1_id), ("surface2", surface2_id)),
    )


def _case_bounds_surface_delete_counts_ex_targets():
    raw = _bounds_case_raw()
    border1_id = _new_id()
    surface2_id = _new_id()
    return BoundsFailureCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "surface2",
                _POLYGON_GEOM,
                _surface2_props(border1_id),
                fid=surface2_id,
            ),
        ),
        (_delete("surface2", surface2_id),),
        (_bounds_structure_finding("border1", border1_id, expected=1, actual=0),),
        (("border1", border1_id), ("surface2", surface2_id)),
    )


def _case_bounds_described_by_note_does_not_count_owner():
    raw = _surface_case_with_described_by_note_target("border4")
    border4_id = _new_id()
    surface_id = _new_id()
    return BoundsFailureCase(
        raw,
        (),
        (
            _insert("border4", _OUTER_RING_GEOM, {"is_bounding": True}, fid=border4_id),
            _insert(
                "surface",
                _POLYGON_GEOM,
                {"describedByNote": [{"featuretype": "border4", "id": border4_id}]},
                fid=surface_id,
            ),
        ),
        (
            _footprint_structure_finding(
                "surface", surface_id, "no_boundary", counts=(0, 0)
            ),
            _bounds_structure_finding("border4", border4_id, expected=1, actual=0),
        ),
    )


def _case_bounds_when_false_does_not_count_owner():
    raw = _bounds_case_raw()
    border4_id = _new_id()
    surface_id = _new_id()
    return BoundsFailureCase(
        raw,
        (),
        (
            _insert(
                "border4", _OUTER_RING_GEOM, {"is_bounding": False}, fid=border4_id
            ),
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(conditional=(border4_id,)),
                fid=surface_id,
            ),
        ),
        (
            _footprint_structure_finding(
                "surface", surface_id, "no_boundary", counts=(1, 0)
            ),
            _bounds_structure_finding("border4", border4_id, expected=1, actual=0),
        ),
    )


def _case_bounds_and_role_conflict_are_both_reported():
    raw = _bounds_case_raw()
    border1_id = _new_id()
    border4_id = _new_id()
    surface2_id = _new_id()
    surface_id = _new_id()
    return BoundsFailureCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "surface2",
                _POLYGON_GEOM,
                _surface2_props(border1_id),
                fid=surface2_id,
            ),
        ),
        (
            _insert("border4", _LINE_GEOM_ALT, {"is_bounding": True}, fid=border4_id),
            _insert(
                "surface",
                _POLYGON_GEOM,
                {
                    "boundedByOuter": [
                        {"featuretype": "border1", "lokalid": border1_id}
                    ],
                    "boundedByConditional": [
                        {"featuretype": "border4", "id": border4_id}
                    ],
                },
                fid=surface_id,
            ),
        ),
        (
            _footprint_structure_finding(
                "surface",
                surface_id,
                "conflicting_boundary_roles",
                counts=(2, 2),
                roles=("boundedByConditional", "boundedByOuter"),
            ),
            _bounds_structure_finding(
                "border1",
                border1_id,
                expected=1,
                actual=2,
                owners=(("surface", surface_id), ("surface2", surface2_id)),
            ),
        ),
        (("border1", border1_id), ("surface2", surface2_id)),
    )


def _case_bounds_curve_without_rule_is_never_reported():
    raw = _bounds_case_raw()
    border3_id = _new_id()
    return BoundsSuccessCase(
        raw,
        (),
        (_insert("border3", _NOTE_LINE_GEOM, {}, fid=border3_id),),
    )


def _case_bounds_delete_and_insert_swap_commits_when_delete_runs_first():
    raw = _bounds_case_raw()
    border1_id = _new_id()
    surface_id = _new_id()
    surface2_id = _new_id()
    return BoundsSuccessCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border1_id,)),
                fid=surface_id,
            ),
        ),
        (
            _delete("surface", surface_id),
            _insert(
                "surface2",
                _POLYGON_GEOM,
                _surface2_props(border1_id),
                fid=surface2_id,
            ),
        ),
    )


def _case_bounds_delete_and_insert_swap_commits_when_insert_runs_first():
    raw = _bounds_case_raw()
    border1_id = _new_id()
    surface_id = _new_id()
    surface2_id = _new_id()
    return BoundsSuccessCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border1_id,)),
                fid=surface_id,
            ),
        ),
        (
            _insert(
                "surface2",
                _POLYGON_GEOM,
                _surface2_props(border1_id),
                fid=surface2_id,
            ),
            _delete("surface", surface_id),
        ),
    )


def _case_bounds_delete_without_replacement_rolls_back():
    raw = _bounds_case_raw()
    border1_id = _new_id()
    surface_id = _new_id()
    return BoundsFailureCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border1_id,)),
                fid=surface_id,
            ),
        ),
        (_delete("surface", surface_id),),
        (_bounds_structure_finding("border1", border1_id, expected=1, actual=0),),
        (("border1", border1_id), ("surface", surface_id)),
    )


def _case_bounds_two_owner_divider_with_two_surfaces_commits():
    raw = _bounds_case_raw()
    border1_a_id = _new_id()
    border1_b_id = _new_id()
    border2_id = _new_id()
    surface_a_id = _new_id()
    surface_b_id = _new_id()
    return BoundsSuccessCase(
        raw,
        (),
        (
            _insert(
                "border1",
                _LINE_GEOM,
                {"identifikasjon": {"lokalid": border1_a_id}},
                fid=border1_a_id,
            ),
            _insert(
                "border1",
                _LINE_GEOM_WIDER,
                {"identifikasjon": {"lokalid": border1_b_id}},
                fid=border1_b_id,
            ),
            _insert(
                "border2",
                _LINE_GEOM_ALT,
                {"identifikasjon": {"lokalid": border2_id}},
                fid=border2_id,
            ),
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border1_a_id,), shared=(border2_id,)),
                fid=surface_a_id,
            ),
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border1_b_id,), shared=(border2_id,)),
                fid=surface_b_id,
            ),
        ),
    )


BOUNDS_FAILURE_CASE_BUILDERS = [
    pytest.param(
        _case_bounds_one_curve_claimed_by_two_surfaces,
        id="bounds-one-curve-claimed-by-two-surfaces",
    ),
    pytest.param(
        _case_bounds_orphan_curve_inserted_without_link,
        id="bounds-orphan-curve-inserted-without-link",
    ),
    pytest.param(
        _case_bounds_two_owner_divider_with_one_surface_fails,
        id="bounds-two-owner-divider-with-one-surface-fails",
    ),
    pytest.param(
        _case_bounds_surface_update_to_empty_counts_ex_target,
        id="bounds-surface-update-to-empty-counts-ex-target",
    ),
    pytest.param(
        _case_bounds_surface_delete_counts_ex_targets,
        id="bounds-surface-delete-counts-ex-targets",
    ),
    pytest.param(
        _case_bounds_described_by_note_does_not_count_owner,
        id="bounds-described-by-note-does-not-count-owner",
    ),
    pytest.param(
        _case_bounds_when_false_does_not_count_owner,
        id="bounds-when-false-does-not-count-owner",
    ),
    pytest.param(
        _case_bounds_and_role_conflict_are_both_reported,
        id="bounds-and-role-conflict-are-both-reported",
    ),
    pytest.param(
        _case_bounds_delete_without_replacement_rolls_back,
        id="bounds-delete-without-replacement-rolls-back",
    ),
]


BOUNDS_SUCCESS_CASE_BUILDERS = [
    pytest.param(
        _case_bounds_curve_without_rule_is_never_reported,
        id="bounds-curve-without-rule-is-never-reported",
    ),
    pytest.param(
        _case_bounds_delete_and_insert_swap_commits_when_delete_runs_first,
        id="bounds-delete-and-insert-swap-commits-when-delete-runs-first",
    ),
    pytest.param(
        _case_bounds_delete_and_insert_swap_commits_when_insert_runs_first,
        id="bounds-delete-and-insert-swap-commits-when-insert-runs-first",
    ),
    pytest.param(
        _case_bounds_two_owner_divider_with_two_surfaces_commits,
        id="bounds-two-owner-divider-with-two-surfaces-commits",
    ),
]


def _case_members_dispatch_keeps_one_row_per_association_when_target_missing():
    raw = _surface_case_with_three_way_alternative()
    border1_id = _new_id()
    border2_id = _new_id()
    border4_id = _new_id()
    surface_id = _new_id()
    return (
        raw,
        (
            _insert(
                "border1",
                _THREE_WAY_OUTER_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "border2",
                _THREE_WAY_SHARED_GEOM,
                {"identifikasjon": {"lokalid": border2_id}},
                fid=border2_id,
            ),
            _insert(
                "border4",
                _THREE_WAY_CONDITIONAL_GEOM,
                {"is_bounding": True},
                fid=border4_id,
            ),
        ),
        _insert(
            "surface",
            _POLYGON_GEOM,
            _surface_props(
                outer=(border1_id,),
                shared=(border2_id,),
                conditional=(border4_id,),
            ),
            fid=surface_id,
        ),
        border4_id,
        surface_id,
    )


def _case_three_collection_ring_is_valid():
    raw = _surface_case_with_three_way_alternative()
    border1_id = _new_id()
    border2_id = _new_id()
    border4_id = _new_id()
    surface_id = _new_id()
    return FootprintGeometrySuccessCase(
        raw,
        (
            _insert(
                "border1",
                _THREE_WAY_OUTER_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "border2",
                _THREE_WAY_SHARED_GEOM,
                {"identifikasjon": {"lokalid": border2_id}},
                fid=border2_id,
            ),
            _insert(
                "border4",
                _THREE_WAY_CONDITIONAL_GEOM,
                {"is_bounding": True},
                fid=border4_id,
            ),
        ),
        (
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(
                    outer=(border1_id,),
                    shared=(border2_id,),
                    conditional=(border4_id,),
                ),
                fid=surface_id,
            ),
        ),
    )


def _case_three_collection_ring_with_one_target_collection_unused_is_valid():
    raw = _surface_case_with_three_way_alternative()
    border1_id = _new_id()
    border2_id = _new_id()
    surface_id = _new_id()
    return FootprintGeometrySuccessCase(
        raw,
        (
            _insert(
                "border1",
                _LINE_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "border2",
                _LINE_GEOM_ALT,
                {"identifikasjon": {"lokalid": border2_id}},
                fid=border2_id,
            ),
        ),
        (
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border1_id,), shared=(border2_id,)),
                fid=surface_id,
            ),
        ),
    )


def _case_crossing_lines_are_nonsimple():
    raw = _case_raw()
    first_id = _new_id()
    second_id = _new_id()
    surface_id = _new_id()
    return FootprintGeometryFailureCase(
        raw,
        (
            _insert(
                "border1",
                _CROSSING_LINE_GEOM,
                {"identifikasjon": {"lokalid": first_id}},
                fid=first_id,
            ),
            _insert(
                "border1",
                _CROSSING_LINE_GEOM_ALT,
                {"identifikasjon": {"lokalid": second_id}},
                fid=second_id,
            ),
        ),
        (
            _insert_without_geometry(
                "surface2", _surface2_props(first_id, second_id), fid=surface_id
            ),
        ),
        (
            _footprint_geometry_finding(
                "surface2", surface_id, "nonsimple_boundary", counts=(2, 2)
            ),
        ),
        expected_absent=(("surface2", surface_id),),
        expected_present=(("border1", first_id), ("border1", second_id)),
    )


def _case_open_lines_do_not_close():
    raw = _case_raw()
    first_id = _new_id()
    second_id = _new_id()
    surface_id = _new_id()
    return FootprintGeometryFailureCase(
        raw,
        (
            _insert(
                "border1",
                _OPEN_LINE_GEOM,
                {"identifikasjon": {"lokalid": first_id}},
                fid=first_id,
            ),
            _insert(
                "border1",
                _OPEN_LINE_GEOM_ALT,
                {"identifikasjon": {"lokalid": second_id}},
                fid=second_id,
            ),
        ),
        (
            _insert_without_geometry(
                "surface2", _surface2_props(first_id, second_id), fid=surface_id
            ),
        ),
        (
            _footprint_geometry_finding(
                "surface2",
                surface_id,
                "boundary_does_not_close",
                counts=(2, 2),
            ),
        ),
        expected_absent=(("surface2", surface_id),),
        expected_present=(("border1", first_id), ("border1", second_id)),
    )


def _case_free_floating_line_is_unused():
    raw = _case_raw()
    ring_id = _new_id()
    free_id = _new_id()
    surface_id = _new_id()
    return FootprintGeometryFailureCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": ring_id}},
                fid=ring_id,
            ),
            _insert(
                "border1",
                _FREE_FLOATING_LINE_GEOM,
                {"identifikasjon": {"lokalid": free_id}},
                fid=free_id,
            ),
        ),
        (
            _insert_without_geometry(
                "surface2", _surface2_props(ring_id, free_id), fid=surface_id
            ),
        ),
        (
            _footprint_geometry_finding(
                "surface2",
                surface_id,
                "unused_boundary_line",
                counts=(2, 2),
                areas=1,
                holes=0,
                unused=(("border1", free_id),),
            ),
        ),
        expected_absent=(("surface2", surface_id),),
        expected_present=(("border1", ring_id), ("border1", free_id)),
    )


def _case_disjoint_rings_fail_surface_areas_one():
    raw = _case_raw()
    outer_id = _new_id()
    shared_id = _new_id()
    surface_id = _new_id()
    return FootprintGeometryFailureCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": outer_id}},
                fid=outer_id,
            ),
            _insert(
                "border2",
                _LINE_GEOM_ALT_2,
                {"identifikasjon": {"lokalid": shared_id}},
                fid=shared_id,
            ),
        ),
        (
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(outer_id,), shared=(shared_id,)),
                fid=surface_id,
            ),
        ),
        (
            _footprint_geometry_finding(
                "surface",
                surface_id,
                "multiple_disjoint_areas",
                counts=(2, 2),
                areas=2,
                holes=0,
            ),
        ),
        expected_absent=(("surface", surface_id),),
        expected_present=(("border1", outer_id), ("border2", shared_id)),
    )


def _case_inner_ring_rejected_on_surface2():
    raw = _case_raw()
    outer_id = _new_id()
    inner_id = _new_id()
    surface_id = _new_id()
    return FootprintGeometryFailureCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": outer_id}},
                fid=outer_id,
            ),
            _insert(
                "border1",
                _INNER_RING_GEOM,
                {"identifikasjon": {"lokalid": inner_id}},
                fid=inner_id,
            ),
        ),
        (
            _insert_without_geometry(
                "surface2", _surface2_props(outer_id, inner_id), fid=surface_id
            ),
        ),
        (
            _footprint_geometry_finding(
                "surface2",
                surface_id,
                "holes_not_allowed",
                counts=(2, 2),
                areas=1,
                holes=1,
            ),
        ),
        expected_absent=(("surface2", surface_id),),
        expected_present=(("border1", outer_id), ("border1", inner_id)),
    )


def _case_structure_gate_blocks_geometry():
    raw = _case_raw()
    border1_id = _new_id()
    border4_id = _new_id()
    surface_id = _new_id()
    return FootprintRuleFailureCase(
        raw,
        (
            _insert(
                "border1",
                _CROSSING_LINE_GEOM,
                {"identifikasjon": {"lokalid": border1_id}},
                fid=border1_id,
            ),
            _insert(
                "border4",
                _CROSSING_LINE_GEOM_ALT,
                {"is_bounding": True},
                fid=border4_id,
            ),
        ),
        (
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(border1_id,), conditional=(border4_id,)),
                fid=surface_id,
            ),
        ),
        (
            _footprint_structure_finding(
                "surface",
                surface_id,
                "conflicting_boundary_roles",
                counts=(2, 2),
                roles=("boundedByConditional", "boundedByOuter"),
            ),
        ),
        (("border1", border1_id), ("border4", border4_id)),
    )


def _case_disjoint_rings_allowed_on_surface2():
    raw = _case_raw()
    first_id = _new_id()
    second_id = _new_id()
    surface_id = _new_id()
    return FootprintGeometrySuccessCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": first_id}},
                fid=first_id,
            ),
            _insert(
                "border1",
                _LINE_GEOM_ALT_2,
                {"identifikasjon": {"lokalid": second_id}},
                fid=second_id,
            ),
        ),
        (
            _insert_without_geometry(
                "surface2", _surface2_props(first_id, second_id), fid=surface_id
            ),
        ),
    )


def _case_inner_ring_allowed_on_surface():
    raw = _case_raw()
    outer_id = _new_id()
    inner_id = _new_id()
    surface_id = _new_id()
    return FootprintGeometrySuccessCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": outer_id}},
                fid=outer_id,
            ),
            _insert(
                "border2",
                _INNER_RING_GEOM,
                {"identifikasjon": {"lokalid": inner_id}},
                fid=inner_id,
            ),
        ),
        (
            _insert(
                "surface",
                _POLYGON_GEOM,
                _surface_props(outer=(outer_id,), shared=(inner_id,)),
                fid=surface_id,
            ),
        ),
    )


def _case_two_surfaces_both_bad_geometry_are_both_reported():
    raw = _case_raw()
    ring_id = _new_id()
    free_id = _new_id()
    surface_a_id, surface_b_id = sorted([_new_id(), _new_id()])
    return FootprintGeometryFailureCase(
        raw,
        (
            _insert(
                "border1",
                _OUTER_RING_GEOM,
                {"identifikasjon": {"lokalid": ring_id}},
                fid=ring_id,
            ),
            _insert(
                "border1",
                _FREE_FLOATING_LINE_GEOM,
                {"identifikasjon": {"lokalid": free_id}},
                fid=free_id,
            ),
        ),
        (
            _insert_without_geometry(
                "surface2", _surface2_props(ring_id, free_id), fid=surface_a_id
            ),
            _insert_without_geometry(
                "surface2", _surface2_props(ring_id, free_id), fid=surface_b_id
            ),
        ),
        (
            _footprint_geometry_finding(
                "surface2",
                surface_a_id,
                "unused_boundary_line",
                counts=(2, 2),
                areas=1,
                holes=0,
                unused=(("border1", free_id),),
            ),
            _footprint_geometry_finding(
                "surface2",
                surface_b_id,
                "unused_boundary_line",
                counts=(2, 2),
                areas=1,
                holes=0,
                unused=(("border1", free_id),),
            ),
        ),
        expected_absent=(("surface2", surface_a_id), ("surface2", surface_b_id)),
        expected_present=(("border1", ring_id), ("border1", free_id)),
    )


FOOTPRINT_GEOMETRY_FAILURE_CASE_BUILDERS = [
    pytest.param(
        _case_crossing_lines_are_nonsimple, id="crossing-lines-nonsimple-boundary"
    ),
    pytest.param(
        _case_open_lines_do_not_close, id="open-lines-boundary-does-not-close"
    ),
    pytest.param(
        _case_free_floating_line_is_unused, id="free-floating-line-unused-boundary-line"
    ),
    pytest.param(
        _case_disjoint_rings_fail_surface_areas_one,
        id="surface-disjoint-rings-multiple-areas",
    ),
    pytest.param(
        _case_inner_ring_rejected_on_surface2,
        id="surface2-inner-ring-holes-not-allowed",
    ),
    pytest.param(
        _case_two_surfaces_both_bad_geometry_are_both_reported,
        id="two-surfaces-both-bad-geometry-reported",
    ),
]


FOOTPRINT_GEOMETRY_SUCCESS_CASE_BUILDERS = [
    pytest.param(
        _case_three_collection_ring_is_valid, id="three-collection-ring-valid"
    ),
    pytest.param(
        _case_three_collection_ring_with_one_target_collection_unused_is_valid,
        id="three-collection-ring-one-target-collection-unused-valid",
    ),
    pytest.param(
        _case_disjoint_rings_allowed_on_surface2, id="surface2-disjoint-rings-valid"
    ),
    pytest.param(_case_inner_ring_allowed_on_surface, id="surface-inner-ring-valid"),
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
    first_id, second_id = sorted([_new_id(), _new_id()])
    _txn(topology_conn, *_border1_ring_pair_items(first_id, second_id))

    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": first_id},
                    {"featuretype": "border1", "lokalid": second_id},
                ],
            },
        ),
    )
    assert report["committed"] is True
    got = _properties(topology_conn, "surface", report["items"][0]["id"])
    assert got["boundedByOuter"] == [
        {"featuretype": "border1", "lokalid": first_id},
        {"featuretype": "border1", "lokalid": second_id},
    ]


def test_create_no_oi_target_by_uuid(topology_conn, borders):
    """A target with no outward_identifier is linked by its row uuid ('id' key)."""
    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            _surface_props(
                outer=(borders["b1a_lokalid"],),
                shared=(borders["b2_lokalid"],),
                notes=(borders["b3_id"],),
            ),
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
            _surface_props(
                outer=(borders["b1a_lokalid"],),
                shared=(borders["b2_lokalid"],),
                notes=(borders["b3_id"],),
            ),
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
            _surface_props(
                outer=(borders["b1a_lokalid"],),
                shared=(borders["b2_lokalid"],),
            ),
        ),
    )

    got = _properties(topology_conn, "surface", report["items"][0]["id"])
    assert got["boundedByShared"] == [
        {"featuretype": "border2", "lokalid": borders["b2_lokalid"]}
    ]


def test_property_with_no_links_is_absent_on_read(topology_conn):
    """A declared property with no links is omitted rather than returned as []."""
    report = _txn(topology_conn, _insert_without_geometry("surface2", {}))

    got = _properties(topology_conn, "surface2", report["items"][0]["id"])
    assert "boundedByOuter" not in got


def test_derived_insert_with_geometry_is_rejected(topology_conn):
    report = _txn(
        topology_conn,
        _insert("surface2", _POLYGON_GEOM, {}, keep_geometry=True),
    )

    _assert_rejected(report)
    assert report["items"][0]["collection"] == "surface2"


def test_derived_update_with_geometry_is_rejected(topology_conn):
    created = _txn(topology_conn, _insert_without_geometry("surface2", {}))
    surface_id = created["items"][0]["id"]

    report = _txn(
        topology_conn,
        _update_with_geometry("surface2", surface_id, _POLYGON_GEOM, {}),
    )

    _assert_rejected(report)
    assert _stored_geometry_meta(topology_conn, "surface2", surface_id)[0] is None


def test_derived_replace_with_geometry_is_rejected(topology_conn):
    created = _txn(topology_conn, _insert_without_geometry("surface2", {}))
    surface_id = created["items"][0]["id"]

    report = _txn(
        topology_conn,
        _replace("surface2", surface_id, _POLYGON_GEOM, {}, keep_geometry=True),
    )

    _assert_rejected(report)
    assert _stored_geometry_meta(topology_conn, "surface2", surface_id)[0] is None


def test_closed_ring_surface_stores_built_geometry(topology_conn):
    ring_id = _new_id()
    _txn(topology_conn, _border1_segment_item(ring_id, _OUTER_RING_GEOM))

    report = _txn(
        topology_conn,
        _insert_without_geometry("surface2", _surface2_props(ring_id)),
    )
    surface_id = report["items"][0]["id"]

    stored_json, geometry_type, part_count = _stored_geometry_meta(
        topology_conn, "surface2", surface_id
    )
    assert stored_json is not None
    assert geometry_type == "MULTIPOLYGON"
    assert part_count == 1
    assert _stored_geometry_equals(topology_conn, "surface2", surface_id, _RING_POLYGON)


def test_member_curve_update_refreshes_stored_footprint(topology_conn):
    first_id = _new_id()
    second_id = _new_id()
    _txn(topology_conn, *_border1_ring_pair_items(first_id, second_id))
    created = _txn(
        topology_conn,
        _insert_without_geometry("surface2", _surface2_props(first_id, second_id)),
    )
    surface_id = created["items"][0]["id"]
    assert _stored_geometry_equals(topology_conn, "surface2", surface_id, _RING_POLYGON)

    updated = _txn(
        topology_conn,
        _update_with_geometry(
            "border1",
            first_id,
            _LINE_GEOM_WIDER,
            {"identifikasjon": {"lokalid": first_id}},
        ),
    )

    assert updated["committed"] is True
    assert _stored_geometry_equals(
        topology_conn, "surface2", surface_id, _WIDER_RING_POLYGON
    )


def test_member_curve_opening_ring_rolls_back_and_keeps_stored_footprint(topology_conn):
    first_id = _new_id()
    second_id = _new_id()
    _txn(topology_conn, *_border1_ring_pair_items(first_id, second_id))
    created = _txn(
        topology_conn,
        _insert_without_geometry("surface2", _surface2_props(first_id, second_id)),
    )
    surface_id = created["items"][0]["id"]

    report = _txn(
        topology_conn,
        _update_with_geometry(
            "border1",
            first_id,
            _OPEN_SHARED_LINE_GEOM,
            {"identifikasjon": {"lokalid": first_id}},
        ),
    )

    _assert_geometry_failure(
        report,
        (
            _footprint_geometry_finding(
                "surface2",
                surface_id,
                "boundary_does_not_close",
                counts=(2, 2),
            ),
        ),
    )
    assert _stored_geometry_equals(topology_conn, "surface2", surface_id, _RING_POLYGON)


def test_shared_curve_update_refreshes_both_stored_footprints(topology_conn, borders):
    shared_id = _new_id()
    surface2_tail_id = _new_id()
    report = _txn(
        topology_conn,
        _insert(
            "border1",
            _LINE_GEOM,
            {"identifikasjon": {"lokalid": shared_id}},
            fid=shared_id,
        ),
        _insert(
            "border1",
            _LINE_GEOM_ALT,
            {"identifikasjon": {"lokalid": surface2_tail_id}},
            fid=surface2_tail_id,
        ),
        _insert_without_geometry(
            "surface",
            _surface_props(outer=(shared_id,), shared=(borders["b2_lokalid"],)),
        ),
        _insert_without_geometry(
            "surface2",
            _surface2_props(shared_id, surface2_tail_id),
        ),
    )
    surface_id = report["items"][2]["id"]
    surface2_id = report["items"][3]["id"]

    updated = _txn(
        topology_conn,
        _update_with_geometry(
            "border1",
            shared_id,
            _LINE_GEOM_WIDER,
            {"identifikasjon": {"lokalid": shared_id}},
        ),
    )

    assert updated["committed"] is True
    assert _stored_geometry_equals(
        topology_conn, "surface", surface_id, _WIDER_RING_POLYGON
    )
    assert _stored_geometry_equals(
        topology_conn, "surface2", surface2_id, _WIDER_RING_POLYGON
    )


def test_optional_boundary_with_no_members_stores_null_geometry(topology_conn):
    report = _txn(topology_conn, _insert_without_geometry("surface2", {}))
    surface_id = report["items"][0]["id"]

    stored_json, geometry_type, part_count = _stored_geometry_meta(
        topology_conn, "surface2", surface_id
    )
    assert stored_json is None
    assert geometry_type is None
    assert part_count is None


def test_disjoint_rings_surface_stores_two_part_multipolygon(db):
    case = _case_disjoint_rings_allowed_on_surface2()
    dataset = case.raw["name"]
    with _topology_case_conn(db, case.raw) as conn:
        setup = _txn(conn, *case.setup_items, dataset=dataset)
        _assert_structure_clean_commit(setup, len(case.setup_items))

        report = _txn(conn, *case.tx_items, dataset=dataset)
        _assert_structure_clean_commit(report, len(case.tx_items))

        surface_id = report["items"][0]["id"]
        stored_json, geometry_type, part_count = _stored_geometry_meta(
            conn, "surface2", surface_id, dataset=dataset
        )
        assert stored_json is not None
        assert geometry_type == "MULTIPOLYGON"
        assert part_count == 2
        assert _stored_geometry_equals(
            conn, "surface2", surface_id, _TWO_RINGS_MULTIPOLYGON, dataset=dataset
        )


def test_three_collection_ring_stores_built_geometry(db):
    case = _case_three_collection_ring_is_valid()
    dataset = case.raw["name"]
    with _topology_case_conn(db, case.raw) as conn:
        setup = _txn(conn, *case.setup_items, dataset=dataset)
        _assert_structure_clean_commit(setup, len(case.setup_items))

        report = _txn(conn, *case.tx_items, dataset=dataset)
        _assert_structure_clean_commit(report, len(case.tx_items))

        surface_id = report["items"][0]["id"]
        assert _stored_geometry_equals(
            conn, "surface", surface_id, _RING_POLYGON, dataset=dataset
        )


def test_update_leaves_unnamed_properties_intact(topology_conn, borders):
    """PATCH: a property absent from the document keeps its existing rows.

    Surface starts with rows under boundedByOuter and describedByNote.
    An update that only names describedByNote must leave boundedByOuter untouched.
    """
    outer_id = _new_id()
    _txn(topology_conn, _border1_segment_item(outer_id, _OUTER_RING_GEOM))

    create_report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [{"featuretype": "border1", "lokalid": outer_id}],
                "describedByNote": [{"featuretype": "border3", "id": borders["b3_id"]}],
            },
        ),
    )
    surface_id = create_report["items"][0]["id"]

    update_report = _txn(
        topology_conn, _update("surface", surface_id, {"describedByNote": []})
    )
    assert update_report["committed"] is True

    got = _properties(topology_conn, "surface", surface_id)
    assert got["boundedByOuter"] == [{"featuretype": "border1", "lokalid": outer_id}]
    assert "describedByNote" not in got


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
            _surface_props(
                outer=(borders["b1a_lokalid"],),
                shared=(borders["b2_lokalid"],),
            ),
        ),
    )
    surface_id = create_report["items"][0]["id"]

    _txn(
        topology_conn,
        _replace(
            "surface",
            surface_id,
            _POLYGON_GEOM,
            _surface_props(conditional=(borders["b4_id"],)),
        ),
    )

    got = _properties(topology_conn, "surface", surface_id)
    assert "boundedByOuter" not in got
    assert got["boundedByConditional"] == [
        {"featuretype": "border4", "id": borders["b4_id"]}
    ]


def test_empty_array_clears_that_property(topology_conn, borders):
    """An empty array in the document clears that property's rows.

    An absent key (PATCH) means 'leave alone'; an empty array means 'remove all'.
    """
    first_id = _new_id()
    second_id = _new_id()
    _txn(topology_conn, *_border1_ring_pair_items(first_id, second_id))

    create_report = _txn(
        topology_conn,
        _insert_without_geometry(
            "surface2",
            _surface2_props(first_id, second_id),
        ),
    )
    surface_id = create_report["items"][0]["id"]

    update_report = _txn(
        topology_conn, _update("surface2", surface_id, {"boundedByOuter": []})
    )
    assert update_report["committed"] is True

    got = _properties(topology_conn, "surface2", surface_id)
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
            _surface_props(
                outer=(borders["b1a_lokalid"],),
                shared=(borders["b2_lokalid"],),
            ),
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
            "border1",
            _OUTER_RING_GEOM,
            {"identifikasjon": {"lokalid": disposable_lokalid}},
        ),
    )
    disposable_id = disposable_report["items"][0]["id"]

    create_report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            _surface_props(outer=(disposable_lokalid,)),
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
    first_id = _new_id()
    second_id = _new_id()
    _txn(topology_conn, *_border1_ring_pair_items(first_id, second_id))

    create_report = _txn(
        topology_conn,
        _insert_without_geometry(
            "surface2",
            _surface2_props(first_id, second_id),
        ),
    )
    surface_id = create_report["items"][0]["id"]

    before = topology_conn.execute(
        'select updated_at from topology.border1 where "id" = %s::uuid',
        (first_id,),
    ).fetchone()[0]

    update_report = _txn(
        topology_conn, _update("surface2", surface_id, {"boundedByOuter": []})
    )
    assert update_report["committed"] is True

    after = topology_conn.execute(
        'select updated_at from topology.border1 where "id" = %s::uuid',
        (first_id,),
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
                "boundedByShared": [
                    {"featuretype": "border2", "lokalid": borders["b2_lokalid"]}
                ],
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
            _surface_props(
                outer=(borders["b1a_lokalid"],),
                shared=(borders["b2_lokalid"],),
                notes=(borders["b3_id"],),
            ),
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
    first_id, second_id = sorted([_new_id(), _new_id()])
    _txn(topology_conn, *_border1_ring_pair_items(first_id, second_id))

    report = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            {
                "boundedByOuter": [
                    {"featuretype": "border1", "lokalid": second_id},
                    {"featuretype": "border1", "lokalid": first_id},
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
            _surface_props(
                outer=(borders["b1a_lokalid"],),
                shared=(borders["b2_lokalid"],),
            ),
        ),
    )
    second = _txn(
        topology_conn,
        _insert(
            "surface",
            _POLYGON_GEOM,
            _surface_props(
                outer=(borders["b1b_lokalid"],),
                shared=(borders["b2_lokalid"],),
                notes=(borders["b3_id"],),
            ),
        ),
    )

    features = _items(topology_conn, "surface")["features"]
    by_id = {str(feature["id"]): feature for feature in features}
    assert by_id[first["items"][0]["id"]]["properties"]["boundedByOuter"] == [
        {"featuretype": "border1", "lokalid": borders["b1a_lokalid"]}
    ]
    assert by_id[second["items"][0]["id"]]["properties"]["boundedByOuter"] == [
        {"featuretype": "border1", "lokalid": borders["b1b_lokalid"]}
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
            "border1",
            _LINE_GEOM_ALT,
            {"identifikasjon": {"lokalid": disposable_lokalid}},
        ),
    )
    report = _txn(
        topology_conn,
        _insert_without_geometry(
            "surface2",
            _surface2_props(borders["b1a_lokalid"], disposable_lokalid),
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
    assert _association_rows(topology_conn, "surface2", surface_id) == expected_rows


def test_sources_using_is_polymorphic_on_source_collection(topology_conn, borders):
    """One target can be referenced from more than one source collection."""
    reverse_id = str(uuid.uuid4())
    closing_id = _new_id()
    report = _txn(
        topology_conn,
        _insert(
            "border1",
            _LINE_GEOM,
            {"identifikasjon": {"lokalid": reverse_id}},
        ),
        _insert(
            "border1",
            _LINE_GEOM_ALT,
            {"identifikasjon": {"lokalid": closing_id}},
            fid=closing_id,
        ),
        _insert(
            "surface",
            _POLYGON_GEOM,
            _surface_props(outer=(reverse_id,), shared=(borders["b2_lokalid"],)),
        ),
        _insert_without_geometry(
            "surface2",
            _surface2_props(reverse_id, closing_id),
        ),
    )
    surface_id = report["items"][2]["id"]
    surface2_id = report["items"][3]["id"]

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
            _LINE_GEOM,
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
            _surface_props(outer=(reverse_a,), shared=(borders["b2_lokalid"],)),
        ),
        _insert_without_geometry(
            "surface2",
            _surface2_props(reverse_b),
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


@pytest.mark.parametrize("case_builder", FOOTPRINT_RULE_FAILURE_CASE_BUILDERS)
def test_structural_checks_one_of_and_when_failures_roll_back_with_findings(
    db, case_builder
):
    case = case_builder()
    dataset = case.raw["name"]
    with _topology_case_conn(db, case.raw) as conn:
        if case.setup_items:
            setup = _txn(conn, *case.setup_items, dataset=dataset)
            _assert_structure_clean_commit(setup, len(case.setup_items))

        report = _txn(conn, *case.tx_items, dataset=dataset)

        _assert_structure_failure(report, case.expected_findings)
        for collection, fid in case.expected_present:
            assert _item(conn, collection, fid, dataset=dataset) is not None


@pytest.mark.parametrize("case_builder", FOOTPRINT_RULE_SUCCESS_CASE_BUILDERS)
def test_structural_checks_one_of_and_when_valid_cases_commit_cleanly(db, case_builder):
    case = case_builder()
    dataset = case.raw["name"]
    with _topology_case_conn(db, case.raw) as conn:
        if case.setup_items:
            setup = _txn(conn, *case.setup_items, dataset=dataset)
            _assert_structure_clean_commit(setup, len(case.setup_items))

        report = _txn(conn, *case.tx_items, dataset=dataset)

        _assert_structure_clean_commit(report, len(case.tx_items))


def _replace_footprint_verdict_with_raise(conn, dataset, function_name):
    signature = "(fid uuid)"
    if function_name.endswith("_geometry_verdict"):
        signature = "(fid uuid, measure topogdb.footprint_measure)"
    conn.execute(
        psycopg.sql.SQL(
            """
create or replace function {}.{}{}
returns jsonb language plpgsql stable as $f$
begin
    raise exception 'sabotage' using errcode = 'XX000';
end;
$f$
"""
        ).format(
            psycopg.sql.Identifier(dataset),
            psycopg.sql.Identifier(function_name),
            psycopg.sql.SQL(signature),
        )
    )


def test_collection_footprint_members_keeps_one_row_per_association_when_target_missing(
    db,
):
    raw, setup_items, surface_item, missing_target_id, surface_id = (
        _case_members_dispatch_keeps_one_row_per_association_when_target_missing()
    )
    dataset = raw["name"]
    with _topology_case_conn(db, raw) as conn:
        setup = _txn(conn, *setup_items, dataset=dataset)
        _assert_structure_clean_commit(setup, len(setup_items))
        surface = _txn(conn, surface_item, dataset=dataset)
        _assert_structure_clean_commit(surface, 1)

        conn.execute(
            psycopg.sql.SQL('delete from {}.border4 where "id" = %s::uuid').format(
                psycopg.sql.Identifier(dataset)
            ),
            (missing_target_id,),
        )

        assert _footprint_members_rows(
            conn, "surface", surface_id, dataset=dataset
        ) == [
            (
                "boundedByConditional",
                "border4",
                missing_target_id,
                False,
                None,
            ),
            (
                "boundedByOuter",
                "border1",
                setup_items[0]["feature"]["id"],
                True,
                "LINESTRING(0 0,20 0)",
            ),
            (
                "boundedByShared",
                "border2",
                setup_items[1]["feature"]["id"],
                True,
                "LINESTRING(20 0,20 20,0 20)",
            ),
        ]


@pytest.mark.parametrize("case_builder", BOUNDS_FAILURE_CASE_BUILDERS)
def test_member_bounds_failures_roll_back_with_findings(db, case_builder):
    case = case_builder()
    dataset = case.raw["name"]
    with _topology_case_conn(db, case.raw) as conn:
        if case.setup_items:
            setup = _txn(conn, *case.setup_items, dataset=dataset)
            _assert_structure_clean_commit(setup, len(case.setup_items))

        report = _txn(conn, *case.tx_items, dataset=dataset)

        _assert_structure_failure(report, case.expected_findings)
        for collection, fid in case.expected_present:
            assert _item(conn, collection, fid, dataset=dataset) is not None


@pytest.mark.parametrize("case_builder", BOUNDS_SUCCESS_CASE_BUILDERS)
def test_member_bounds_valid_cases_commit_cleanly(db, case_builder):
    case = case_builder()
    dataset = case.raw["name"]
    with _topology_case_conn(db, case.raw) as conn:
        if case.setup_items:
            setup = _txn(conn, *case.setup_items, dataset=dataset)
            _assert_structure_clean_commit(setup, len(case.setup_items))

        report = _txn(conn, *case.tx_items, dataset=dataset)

        _assert_structure_clean_commit(report, len(case.tx_items))


def test_structure_findings_omit_unmeasured_area_and_hole_counts(db):
    case = _case_outer_and_conditional_true_conflict()
    dataset = case.raw["name"]
    with _topology_case_conn(db, case.raw) as conn:
        setup = _txn(conn, *case.setup_items, dataset=dataset)
        _assert_structure_clean_commit(setup, len(case.setup_items))

        report = _txn(conn, *case.tx_items, dataset=dataset)

        finding = report["structure"][0]
        assert "areas" not in finding
        assert "holes" not in finding


def test_document_errors_report_document_phase(topology_conn):
    report = _txn_doc(topology_conn, {"semantic": "bogus", "transaction": []})

    _assert_raised_phase_failure(
        report,
        phase="document",
        sqlstate="P0001",
        reason_substring="unsupported semantic",
    )


def test_structure_verdict_raise_reports_structure_phase(db):
    case = _case_outer_and_shared_are_valid()
    dataset = case.raw["name"]
    with _topology_case_conn(db, case.raw) as conn:
        setup = _txn(conn, *case.setup_items, dataset=dataset)
        _assert_structure_clean_commit(setup, len(case.setup_items))
        _replace_footprint_verdict_with_raise(
            conn, dataset, "_surface_footprint_structure_verdict"
        )

        report = _txn(conn, *case.tx_items, dataset=dataset)

        _assert_raised_phase_failure(
            report,
            phase="structure",
            sqlstate="XX000",
            reason_substring="sabotage",
        )


def test_geometry_verdict_raise_reports_geometry_phase(db):
    case = _case_outer_and_shared_are_valid()
    dataset = case.raw["name"]
    with _topology_case_conn(db, case.raw) as conn:
        setup = _txn(conn, *case.setup_items, dataset=dataset)
        _assert_structure_clean_commit(setup, len(case.setup_items))
        _replace_footprint_verdict_with_raise(
            conn, dataset, "_surface_footprint_geometry_verdict"
        )

        report = _txn(conn, *case.tx_items, dataset=dataset)

        _assert_raised_phase_failure(
            report,
            phase="geometry",
            sqlstate="XX000",
            reason_substring="sabotage",
        )


def test_transaction_report_always_includes_top_level_sqlstate(db):
    committed_case = _case_outer_and_shared_are_valid()
    rejected_id = _new_id()
    structure_case = _case_outer_and_conditional_true_conflict()

    committed_dataset = committed_case.raw["name"]
    with _topology_case_conn(db, committed_case.raw) as conn:
        setup = _txn(conn, *committed_case.setup_items, dataset=committed_dataset)
        _assert_structure_clean_commit(setup, len(committed_case.setup_items))
        committed = _txn(conn, *committed_case.tx_items, dataset=committed_dataset)
        assert committed["sqlstate"] is None

    with _topology_case_conn(db, _case_raw()) as conn:
        rejected = _txn(
            conn,
            _insert(
                "surface2",
                _POLYGON_GEOM,
                _surface2_props(rejected_id),
                fid=_new_id(),
                keep_geometry=True,
            ),
            dataset="topology",
        )
        assert "sqlstate" in rejected
        assert rejected["sqlstate"] is None

    structure_dataset = structure_case.raw["name"]
    with _topology_case_conn(db, structure_case.raw) as conn:
        setup = _txn(conn, *structure_case.setup_items, dataset=structure_dataset)
        _assert_structure_clean_commit(setup, len(structure_case.setup_items))
        structure = _txn(conn, *structure_case.tx_items, dataset=structure_dataset)
        assert structure["sqlstate"] is None

    raised_case = _case_outer_and_shared_are_valid()
    raised_dataset = raised_case.raw["name"]
    with _topology_case_conn(db, raised_case.raw) as conn:
        setup = _txn(conn, *raised_case.setup_items, dataset=raised_dataset)
        _assert_structure_clean_commit(setup, len(raised_case.setup_items))
        _replace_footprint_verdict_with_raise(
            conn, raised_dataset, "_surface_footprint_geometry_verdict"
        )
        raised = _txn(conn, *raised_case.tx_items, dataset=raised_dataset)
        assert raised["sqlstate"] == "XX000"


@pytest.mark.parametrize("case_builder", FOOTPRINT_GEOMETRY_FAILURE_CASE_BUILDERS)
def test_geometry_checks_roll_back_with_findings(db, case_builder):
    case = case_builder()
    dataset = case.raw["name"]
    with _topology_case_conn(db, case.raw) as conn:
        if case.setup_items:
            setup = _txn(conn, *case.setup_items, dataset=dataset)
            _assert_structure_clean_commit(setup, len(case.setup_items))

        report = _txn(conn, *case.tx_items, dataset=dataset)

        _assert_geometry_failure(report, case.expected_findings)
        for collection, fid in case.expected_absent:
            assert _item(conn, collection, fid, dataset=dataset) is None
        for collection, fid in case.expected_present:
            assert _item(conn, collection, fid, dataset=dataset) is not None


@pytest.mark.parametrize("case_builder", FOOTPRINT_GEOMETRY_SUCCESS_CASE_BUILDERS)
def test_geometry_checks_valid_cases_commit_cleanly(db, case_builder):
    case = case_builder()
    dataset = case.raw["name"]
    with _topology_case_conn(db, case.raw) as conn:
        if case.setup_items:
            setup = _txn(conn, *case.setup_items, dataset=dataset)
            _assert_structure_clean_commit(setup, len(case.setup_items))

        report = _txn(conn, *case.tx_items, dataset=dataset)

        _assert_structure_clean_commit(report, len(case.tx_items))


def test_structure_phase_gates_geometry_phase(db):
    case = _case_structure_gate_blocks_geometry()
    dataset = case.raw["name"]
    with _topology_case_conn(db, case.raw) as conn:
        setup = _txn(conn, *case.setup_items, dataset=dataset)
        _assert_structure_clean_commit(setup, len(case.setup_items))

        report = _txn(conn, *case.tx_items, dataset=dataset)

        _assert_structure_failure(report, case.expected_findings)
        for collection, fid in case.expected_present:
            assert _item(conn, collection, fid, dataset=dataset) is not None


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
