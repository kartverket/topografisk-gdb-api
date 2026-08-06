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


def _sample_feature(coll):
    props = {f.name: _value(f.sql_type) for f in coll.fields if f.required}
    if any(f.name == "source" for f in coll.fields):
        props["source"] = "orig"
    return {
        "type": "Feature",
        "geometry": _GEOM[coll.geometry_type],
        "properties": props,
    }


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
                changed = next((f for f in coll.fields if f.name != "source"), None)
                if changed and witness:
                    cur.execute(
                        "select ogc.feature_update(%s,%s,%s,%s)",
                        (
                            d.name,
                            coll.name,
                            fid,
                            orjson.dumps(
                                {
                                    "properties": {
                                        changed.name: _value(changed.sql_type, 1)
                                    }
                                }
                            ).decode(),
                        ),
                    )
                    props = _item(cur, d.name, coll.name, fid)["properties"]
                    assert props[changed.name] == _value(changed.sql_type, 1)
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
