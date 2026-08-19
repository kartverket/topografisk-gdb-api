"""Language-agnostic DB contract: the ``ogc.feature_*`` dispatch surface.

These tests connect to PostGIS and call ONLY the public dispatch functions with
OGC identifiers ``(dataset, collection)`` — never a table or internal function
name, never any geocomponents Python internals. Any database that exposes the same
``ogc.feature_*`` contract (in any language) passes them unchanged.

They are *generic*: the checks are derived from each dataset description, so they
apply to any dataset. A couple of *fixed* golden assertions pin the examples.
"""

from __future__ import annotations

import orjson
import psycopg
import pytest

_GEOM = {
    "Point": {"type": "Point", "coordinates": [10, 55]},
    "MultiPoint": {"type": "MultiPoint", "coordinates": [[10, 55]]},
    "LineString": {"type": "LineString", "coordinates": [[10, 55], [11, 56]]},
    "MultiLineString": {
        "type": "MultiLineString",
        "coordinates": [[[10, 55], [11, 56]]],
    },
    "Polygon": {
        "type": "Polygon",
        "coordinates": [[[10, 55], [10, 56], [11, 56], [11, 55], [10, 55]]],
    },
    "MultiPolygon": {
        "type": "MultiPolygon",
        "coordinates": [[[[10, 55], [10, 56], [11, 56], [11, 55], [10, 55]]]],
    },
}
_DEFAULT_GEOMETRY = object()
_OMIT_GEOMETRY = object()


def _value(sql_type, variant=0):
    s = sql_type.lower()
    if s == "integer":
        return 1 + variant
    if s in ("double precision", "real", "numeric"):
        return 1.0 + variant
    if s == "boolean":
        return variant == 0
    if s in ("timestamptz", "timestamp with time zone", "timestamp"):
        return "2026-01-01T00:00:00Z" if variant == 0 else "2026-02-01T00:00:00Z"
    if s == "date":
        return "2026-01-01" if variant == 0 else "2026-02-01"
    return "x" if variant == 0 else "y"


def _field_value(f, variant=0):
    """Pick a value for *f* that satisfies DB constraints (codelist, jsonb shape)."""
    if f.codelist_values:
        return f.codelist_values[variant % len(f.codelist_values)]
    if f.sql_type == "jsonb":
        # Provide a proper object so #- path operators don't fail on scalars.
        return {sf.name: _field_value(sf, variant) for sf in f.sub_fields}
    return _value(f.sql_type, variant)


def _sample_feature(coll, *, geometry=_DEFAULT_GEOMETRY, properties=None):
    props = {
        f.name: _field_value(f)
        for f in coll.fields
        if f.required and not f.auto_increment
    }
    if any(f.name == "source" for f in coll.fields):
        props["source"] = "orig"
    if properties:
        props.update(properties)
    feature = {
        "type": "Feature",
        "properties": props,
    }
    if geometry is not _OMIT_GEOMETRY:
        feature["geometry"] = (
            _GEOM[coll.geometry_type] if geometry is _DEFAULT_GEOMETRY else geometry
        )
    return feature


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
def test_items_returns_valid_featurecollection_for_every_collection(datasets, conn):
    with conn.cursor() as cur:
        for d in datasets:
            for coll in d.collections:
                fc = _items(cur, d.name, coll.name)
                assert fc["type"] == "FeatureCollection"
                assert isinstance(fc["features"], list)
                assert isinstance(fc["numberReturned"], int)
                assert "numberMatched" in fc  # with_matched default true


def test_with_matched_toggles_numbermatched(datasets, conn):
    with conn.cursor() as cur:
        for d in datasets:
            for coll in d.collections:
                assert "numberMatched" not in _items(
                    cur, d.name, coll.name, with_matched=False
                )


def test_simple_collections_support_full_crud_roundtrip(datasets, conn):
    with conn.cursor() as cur:
        for d in datasets:
            for coll in d.collections:
                if not coll.supports_crud:
                    continue
                feat = _sample_feature(coll)
                fid = _create(cur, d.name, coll.name, feat)

                got = _item(cur, d.name, coll.name, fid)
                assert got["type"] == "Feature"
                assert str(got["id"]) == str(fid)

                # Partial update changes only the sent property; `source`
                # (set to "orig" at create) is the untouched witness.
                witness = any(f.name == "source" for f in coll.fields)
                changed = next(
                    (
                        f
                        for f in coll.fields
                        if f.name != "source" and not f.auto_increment
                    ),
                    None,
                )
                if changed and witness:
                    cur.execute(
                        "select ogc.feature_update(%s,%s,%s,%s)",
                        (
                            d.name,
                            coll.name,
                            fid,
                            orjson.dumps(
                                {"properties": {changed.name: _field_value(changed, 1)}}
                            ).decode(),
                        ),
                    )
                    props = _item(cur, d.name, coll.name, fid)["properties"]
                    assert props[changed.name] == _field_value(changed, 1)
                    assert props["source"] == "orig"  # untouched

                cur.execute(
                    "select ogc.feature_delete(%s,%s,%s)", (d.name, coll.name, fid)
                )
                assert cur.fetchone()[0] is True
                assert _item(cur, d.name, coll.name, fid) is None


def test_topology_collections_reject_writes_at_the_db(datasets, conn):
    with conn.cursor() as cur:
        for d in datasets:
            for coll in d.collections:
                if coll.supports_crud:
                    continue
                # No internal write function exists → the dispatch call errors.
                # (autocommit: the failed statement is its own transaction.)
                with pytest.raises(psycopg.Error):
                    _create(cur, d.name, coll.name, _sample_feature(coll))
                # Reads still work.
                assert _items(cur, d.name, coll.name)["type"] == "FeatureCollection"


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
