"""Contract tests for the geometry write contract (validity + simplicity).

Cases 3 and 6 earn their place:
  3 — closed ring LineString is accepted, proving the simplicity check does not
      break boundary curves that form rings.
  6 — MultiPolygon touching at an edge is rejected by validity, proving validity
      was not silently replaced by the new simplicity check.
"""

from __future__ import annotations

from dataclasses import dataclass

import orjson
import psycopg
import pytest
from conftest import _schema_conn

from geocomponents.descriptions.models import ResolvedCollection, ResolvedDataset
from geocomponents.schema.build import build_schema_plan

# ── Minimal fixture dataset ───────────────────────────────────────────────────

_DS = "test_geom"
_DATASET = ResolvedDataset(
    name=_DS,
    title="Geometry write contract",
    description="",
    collections=(
        ResolvedCollection(
            name="line",
            title="",
            description="",
            feature_model="simple",
            geometry_type="LineString",
            srid=4326,
            fields=(),
            relationships=(),
        ),
        ResolvedCollection(
            name="mline",
            title="",
            description="",
            feature_model="simple",
            geometry_type="MultiLineString",
            srid=4326,
            fields=(),
            relationships=(),
        ),
        ResolvedCollection(
            name="poly",
            title="",
            description="",
            feature_model="simple",
            geometry_type="Polygon",
            srid=4326,
            fields=(),
            relationships=(),
        ),
        ResolvedCollection(
            name="mpoly",
            title="",
            description="",
            feature_model="simple",
            geometry_type="MultiPolygon",
            srid=4326,
            fields=(),
            relationships=(),
        ),
        ResolvedCollection(
            name="pt",
            title="",
            description="",
            feature_model="simple",
            geometry_type="Point",
            srid=4326,
            fields=(),
            relationships=(),
        ),
    ),
)

# ── Geometry constants ────────────────────────────────────────────────────────

# ST_IsSimple=False, ST_IsValid=True — caught by simplicity only
_CROSSING_LINE = {"type": "LineString", "coordinates": [[0, 0], [2, 2], [0, 2], [2, 0]]}
_CROSSING_MLINE = {
    "type": "MultiLineString",
    "coordinates": [[[0, 0], [2, 2]], [[0, 2], [2, 0]]],
}

# ST_IsSimple=True (closed rings are simple)
_CLOSED_RING_LINE = {
    "type": "LineString",
    "coordinates": [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]],
}

# ST_IsSimple=True (parts touch only at shared endpoints)
_TOUCHING_MLINE = {
    "type": "MultiLineString",
    "coordinates": [[[0, 0], [1, 0]], [[1, 0], [2, 0]]],
}

# ST_IsValid=False, ST_IsSimple=False — caught by either
_BOWTIE_POLY = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]],
}

# ST_IsValid=False, ST_IsSimple=True — caught by validity only (case 6)
_EDGE_MPOLY = {
    "type": "MultiPolygon",
    "coordinates": [
        [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
        [[[2, 0], [4, 0], [4, 2], [2, 2], [2, 0]]],
    ],
}

# valid, simple
_POLY_WITH_HOLE = {
    "type": "Polygon",
    "coordinates": [
        [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
        [[2, 2], [8, 2], [8, 8], [2, 8], [2, 2]],
    ],
}
_POINT = {"type": "Point", "coordinates": [1.0, 2.0]}


# ── Case table ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GeomCase:
    id: str
    collection: str
    geometry: dict | None  # None → feature carries no geometry key
    expected_sqlstate: str | None  # None → accepted


CASES = [
    GeomCase("self-crossing-linestring", "line", _CROSSING_LINE, "P0001"),
    GeomCase("crossing-multilinestring", "mline", _CROSSING_MLINE, "P0001"),
    GeomCase("closed-ring-linestring", "line", _CLOSED_RING_LINE, None),
    GeomCase("touching-endpoints-multilinestring", "mline", _TOUCHING_MLINE, None),
    GeomCase("bowtie-polygon", "poly", _BOWTIE_POLY, "P0001"),
    GeomCase("edge-touching-multipolygon", "mpoly", _EDGE_MPOLY, "P0001"),
    GeomCase("polygon-with-hole", "poly", _POLY_WITH_HOLE, None),
    GeomCase("valid-point", "pt", _POINT, None),
    GeomCase("absent-geometry", "line", None, "P0001"),
]

_ACCEPTED = [c for c in CASES if c.expected_sqlstate is None]
_REJECTED = [c for c in CASES if c.expected_sqlstate is not None]


# ── Fixture ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def geom_conn(db):
    with _schema_conn(db, build_schema_plan(_DATASET)) as conn:
        yield conn


# ── Helpers ───────────────────────────────────────────────────────────────────


def _feature(geometry: dict | None) -> dict:
    if geometry is None:
        return {"type": "Feature", "properties": {}}
    return {"type": "Feature", "geometry": geometry, "properties": {}}


def _create(conn, collection: str, geometry: dict | None) -> str:
    row = conn.execute(
        "select ogc.feature_create(%s, %s, %s)",
        (_DS, collection, orjson.dumps(_feature(geometry)).decode()),
    ).fetchone()
    return str(row[0])


def _update(conn, collection: str, fid: str, feature: dict) -> bool:
    row = conn.execute(
        "select ogc.feature_update(%s, %s, %s, %s)",
        (_DS, collection, fid, orjson.dumps(feature).decode()),
    ).fetchone()
    return row[0]


def _fetch(conn, collection: str, fid: str) -> dict | None:
    row = conn.execute(
        "select ogc.feature_item(%s, %s, %s::uuid)",
        (_DS, collection, fid),
    ).fetchone()
    return row[0] if row else None


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", _ACCEPTED, ids=[c.id for c in _ACCEPTED])
def test_geometry_accepted(geom_conn, case: GeomCase):
    """Valid and simple geometries are stored without error."""
    fid = _create(geom_conn, case.collection, case.geometry)
    assert _fetch(geom_conn, case.collection, fid) is not None


@pytest.mark.parametrize("case", _REJECTED, ids=[c.id for c in _REJECTED])
def test_geometry_rejected(geom_conn, case: GeomCase):
    """Invalid or non-simple geometries are rejected with P0001."""
    with pytest.raises(psycopg.Error) as exc:
        _create(geom_conn, case.collection, case.geometry)
    assert exc.value.sqlstate == case.expected_sqlstate


def test_update_without_geometry_key_leaves_geometry_unchanged(geom_conn):
    """PATCH semantics: a feature_update without a geometry key preserves stored geometry."""
    fid = _create(geom_conn, "line", _CLOSED_RING_LINE)
    stored = _fetch(geom_conn, "line", fid)["geometry"]
    _update(geom_conn, "line", fid, {"type": "Feature", "properties": {}})
    assert _fetch(geom_conn, "line", fid)["geometry"] == stored
