"""Shared feature builders for the DB-backed contract suites."""

from __future__ import annotations

import uuid as _uuid_mod

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
    """Pick a value for *f* that satisfies DB constraints."""
    if f.codelist_values:
        return f.codelist_values[variant % len(f.codelist_values)]
    if f.sql_type == "jsonb":
        return {sf.name: _field_value(sf, variant) for sf in f.sub_fields}
    return _value(f.sql_type, variant)


def _sample_feature(coll, *, geometry=_DEFAULT_GEOMETRY, properties=None, fid=None):
    props = {
        f.name: _field_value(f)
        for f in coll.fields
        if f.required and not f.auto_increment
    }
    if any(f.name == "source" for f in coll.fields):
        props["source"] = "orig"
    if properties:
        props.update(properties)
    # If the collection declares an outward identifier that is a JSONB sub-key,
    # ensure that sub-key is a valid UUID (it becomes the row id on insert).
    if coll.outward_identifier_path and "." in coll.outward_identifier_path:
        oi_col, oi_key = coll.outward_identifier_path.split(".", 1)
        if oi_col in props and isinstance(props[oi_col], dict):
            props[oi_col][oi_key] = (
                str(fid) if fid is not None else str(_uuid_mod.uuid4())
            )
    feature = {
        "type": "Feature",
        "properties": props,
    }
    if fid is not None:
        feature["id"] = str(fid)
    if geometry is not _OMIT_GEOMETRY:
        feature["geometry"] = (
            _GEOM[coll.geometry_type] if geometry is _DEFAULT_GEOMETRY else geometry
        )
    return feature
