"""Language-agnostic DB contract: the ``ogc.feature_*`` dispatch surface.

These tests connect to PostGIS and call ONLY the public dispatch functions with
OGC identifiers ``(dataset, collection)`` — never a table or internal function
name, never any geocomponents Python internals. Any database that exposes the same
``ogc.feature_*`` contract (in any language) passes them unchanged.

They are *generic*: the checks are derived from each dataset description, so they
apply to any dataset. A couple of *fixed* golden assertions pin the examples.
"""

from __future__ import annotations

from uuid import uuid4

import orjson
import psycopg
import pytest
from fixtures.collection_cases import (
    COLLECTION_CASES,
    SIMPLE_CASES,
    TOPOLOGY_CASES,
    CollectionCase,
)
from fixtures.features import _GEOM, _OMIT_GEOMETRY, _field_value, _sample_feature


# -- thin wrappers over the contract surface --------------------------------
def _items(cur, ds, coll, bbox=None, lim=10, off=0, with_matched=True):  # noqa: PLR0913, PLR0917 - mirrors the ogc.feature_items dispatch signature
    cur.execute(
        "select ogc.feature_items(%s,%s,%s,%s,%s,%s)",
        (ds, coll, bbox, lim, off, with_matched),
    )
    return cur.fetchone()[0]


def _item(cur, ds, coll, fid):
    cur.execute("select ogc.feature_item(%s,%s,%s)", (ds, coll, fid))
    return cur.fetchone()[0]


def _create(cur, ds, coll, feature):
    cur.execute(
        "select ogc.feature_create(%s,%s,%s)",
        (ds, coll, orjson.dumps(feature).decode()),
    )
    return cur.fetchone()[0]


def _replace(cur, ds, coll, fid, feature):
    cur.execute(
        "select ogc.feature_replace(%s,%s,%s,%s)",
        (ds, coll, fid, orjson.dumps(feature).decode()),
    )
    return cur.fetchone()[0]


def _update(cur, ds, coll, fid, feature):
    cur.execute(
        "select ogc.feature_update(%s,%s,%s,%s)",
        (ds, coll, fid, orjson.dumps(feature).decode()),
    )
    return cur.fetchone()[0]


def _delete(cur, ds, coll, fid):
    cur.execute("select ogc.feature_delete(%s,%s,%s)", (ds, coll, fid))
    return cur.fetchone()[0]


def _delete_all(cur, ds, coll):
    cur.execute("select ogc.feature_delete_all(%s,%s)", (ds, coll))
    return cur.fetchone()[0]


def _upsert(cur, ds, coll, feature):
    cur.execute(
        "select ogc.feature_upsert(%s,%s,%s)",
        (ds, coll, orjson.dumps(feature).decode()),
    )
    return cur.fetchone()[0]


def _write_entrypoints(cur):
    cur.execute(
        """
        select p.proname
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'ogc'
          and p.proname like 'feature_%'
          and p.proname not in ('feature_item', 'feature_items')
        order by p.proname
        """
    )
    return [row[0].removeprefix("feature_") for row in cur.fetchall()]


def _call_write_entrypoint(cur, op, ds, coll, feature):
    fid = uuid4()
    if op == "create":
        return _create(cur, ds, coll, feature)
    if op == "delete":
        return _delete(cur, ds, coll, fid)
    if op == "delete_all":
        return _delete_all(cur, ds, coll)
    if op == "replace":
        return _replace(cur, ds, coll, fid, feature)
    if op == "update":
        return _update(cur, ds, coll, fid, feature)
    if op == "upsert":
        return _upsert(cur, ds, coll, feature)
    raise AssertionError(f"unhandled public write entrypoint: {op}")


def _collection(datasets, dataset_name, collection_name):
    for dataset in datasets:
        if dataset.name != dataset_name:
            continue
        for collection in dataset.collections:
            if collection.name == collection_name:
                return collection
    raise AssertionError(f"missing collection {dataset_name}.{collection_name}")


# ===========================================================================
# Generic (derived from the descriptions)
# ===========================================================================
@pytest.mark.parametrize(
    "case", COLLECTION_CASES, ids=[case.id for case in COLLECTION_CASES]
)
def test_items_returns_valid_featurecollection_for_every_collection(
    case: CollectionCase, conn
):
    with conn.cursor() as cur:
        fc = _items(cur, case.dataset, case.collection.name)
        assert fc["type"] == "FeatureCollection"
        assert isinstance(fc["features"], list)
        assert isinstance(fc["numberReturned"], int)
        assert "numberMatched" in fc  # with_matched default true


@pytest.mark.parametrize(
    "case", COLLECTION_CASES, ids=[case.id for case in COLLECTION_CASES]
)
def test_with_matched_toggles_numbermatched(case: CollectionCase, conn):
    with conn.cursor() as cur:
        assert "numberMatched" not in _items(
            cur, case.dataset, case.collection.name, with_matched=False
        )


@pytest.mark.parametrize("case", SIMPLE_CASES, ids=[case.id for case in SIMPLE_CASES])
def test_simple_collections_support_full_crud_roundtrip(case: CollectionCase, conn):
    with conn.cursor() as cur:
        coll = case.collection
        feat = _sample_feature(coll)
        fid = _create(cur, case.dataset, coll.name, feat)

        got = _item(cur, case.dataset, coll.name, fid)
        assert got["type"] == "Feature"
        assert str(got["id"]) == str(fid)

        # Partial update changes only the sent property; `source`
        # (set to "orig" at create) is the untouched witness.
        witness = any(f.name == "source" for f in coll.fields)
        changed = next(
            (f for f in coll.fields if f.name != "source" and not f.auto_increment),
            None,
        )
        if changed and witness:
            cur.execute(
                "select ogc.feature_update(%s,%s,%s,%s)",
                (
                    case.dataset,
                    coll.name,
                    fid,
                    orjson.dumps(
                        {"properties": {changed.name: _field_value(changed, 1)}}
                    ).decode(),
                ),
            )
            props = _item(cur, case.dataset, coll.name, fid)["properties"]
            assert props[changed.name] == _field_value(changed, 1)
            assert props["source"] == "orig"  # untouched

        cur.execute(
            "select ogc.feature_delete(%s,%s,%s)", (case.dataset, coll.name, fid)
        )
        assert cur.fetchone()[0] is True
        assert _item(cur, case.dataset, coll.name, fid) is None


@pytest.mark.parametrize(
    "case", TOPOLOGY_CASES, ids=[case.id for case in TOPOLOGY_CASES]
)
def test_topology_collections_reject_writes_at_the_db(case: CollectionCase, conn):
    with conn.cursor() as cur:
        write_ops = _write_entrypoints(cur)
        coll = case.collection
        for op in write_ops:
            with pytest.raises(psycopg.errors.RaiseException) as excinfo:
                _call_write_entrypoint(
                    cur,
                    op,
                    case.dataset,
                    coll.name,
                    _sample_feature(coll),
                )
            assert excinfo.value.sqlstate == "P0001"
        # Reads still work.
        assert _items(cur, case.dataset, coll.name)["type"] == "FeatureCollection"


def test_create_without_geometry_is_rejected(datasets, conn):
    coll = _collection(datasets, "cadastre", "parcels")
    feature = _sample_feature(coll, geometry=_OMIT_GEOMETRY)

    with conn.cursor() as cur, pytest.raises(psycopg.errors.RaiseException) as excinfo:
        # autocommit: the failed statement is its own transaction.
        _create(cur, "cadastre", "parcels", feature)

    assert excinfo.value.sqlstate == "P0001"


def test_create_with_null_geometry_is_rejected(datasets, conn):
    coll = _collection(datasets, "cadastre", "parcels")
    feature = _sample_feature(coll, geometry=None)

    with conn.cursor() as cur, pytest.raises(psycopg.errors.RaiseException) as excinfo:
        _create(cur, "cadastre", "parcels", feature)

    assert excinfo.value.sqlstate == "P0001"


def test_create_with_invalid_geometry_payload_is_rejected(datasets, conn):
    coll = _collection(datasets, "cadastre", "parcels")
    feature = _sample_feature(coll, geometry="nonsense")

    with conn.cursor() as cur, pytest.raises(psycopg.errors.RaiseException) as excinfo:
        _create(cur, "cadastre", "parcels", feature)

    assert excinfo.value.sqlstate == "P0001"


def test_replace_without_geometry_is_rejected(datasets, conn):
    coll = _collection(datasets, "cadastre", "parcels")

    with conn.cursor() as cur, pytest.raises(psycopg.errors.RaiseException) as excinfo:
        fid = _create(cur, "cadastre", "parcels", _sample_feature(coll))
        replacement = _sample_feature(
            coll,
            geometry=_OMIT_GEOMETRY,
            properties={"label": "replaced"},
        )
        _replace(cur, "cadastre", "parcels", fid, replacement)

    assert excinfo.value.sqlstate == "P0001"


def test_update_without_geometry_keeps_existing_geometry(datasets, conn):
    coll = _collection(datasets, "cadastre", "parcels")

    with conn.cursor() as cur:
        fid = _create(cur, "cadastre", "parcels", _sample_feature(coll))
        before = _item(cur, "cadastre", "parcels", fid)
        assert before is not None

        _update(
            cur,
            "cadastre",
            "parcels",
            fid,
            {"properties": {"label": "patched-without-geometry"}},
        )

        after = _item(cur, "cadastre", "parcels", fid)
        assert after is not None
        assert after["geometry"] == before["geometry"]
        assert after["properties"]["label"] == "patched-without-geometry"


def test_update_with_null_geometry_is_rejected(datasets, conn):
    coll = _collection(datasets, "cadastre", "parcels")

    with conn.cursor() as cur, pytest.raises(psycopg.errors.RaiseException) as excinfo:
        fid = _create(cur, "cadastre", "parcels", _sample_feature(coll))
        _update(
            cur,
            "cadastre",
            "parcels",
            fid,
            {
                "geometry": None,
                "properties": {"label": "patched-null-geometry"},
            },
        )

    assert excinfo.value.sqlstate == "P0001"


# ===========================================================================
# Fixed golden (the example dataset)
# ===========================================================================
def test_golden_parcels_feature_shape(conn):
    with conn.cursor() as cur:
        fid = _create(
            cur,
            "cadastre",
            "parcels",
            {
                "type": "Feature",
                "geometry": _GEOM["MultiPolygon"],
                "properties": {
                    "label": "G1",
                    "municipality": "0101",
                    "status": "active",
                    "area_m2": 5.0,
                    "source": "golden",
                },
            },
        )
        feat = _item(cur, "cadastre", "parcels", fid)
        assert feat["geometry"]["type"] == "MultiPolygon"
        assert {
            "label",
            "municipality",
            "status",
            "area_m2",
            "source",
            "created_at",
            "updated_at",
        } <= set(feat["properties"])
        cur.execute("select ogc.feature_delete(%s,%s,%s)", ("cadastre", "parcels", fid))
