"""Contract tests for the outward-identifier-is-the-id rule."""

from __future__ import annotations

import uuid as _uuid_mod
from dataclasses import dataclass
from pathlib import Path

import orjson
import psycopg
import pytest
import yaml
from conftest import _schema_conn

from geocomponents.descriptions.loader import resolve_dataset
from geocomponents.descriptions.models import Commons, DatasetDef
from geocomponents.schema.build import build_schema_plan

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "oi_fixture.yaml"


def _load_dataset():
    raw = yaml.safe_load(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return resolve_dataset(DatasetDef.model_validate(raw), Commons())


_DATASET = _load_dataset()
_DS = _DATASET.name
_COLL = "with_oi"
_PLAIN = "no_oi"
_GEOM = {"type": "LineString", "coordinates": [[10.0, 55.0], [11.0, 56.0]]}


def _u(n: int) -> str:
    """Deterministic UUID from integer; no hand-typed hex strings."""
    return str(_uuid_mod.UUID(int=n))


# Only two named constants; everything else is inline _u(n).
_A = _u(0xA)  # identity via feature.id
_B = _u(0xB)  # identity via OI path


@pytest.fixture(scope="module")
def oid_conn(db):
    with _schema_conn(db, build_schema_plan(_DATASET)) as conn:
        yield conn


def _feature(*, fid: str | None = None, testoi: str | None = None) -> dict:
    props: dict = {"identification": {}}
    if testoi is not None:
        props["identification"]["testoi"] = testoi
    f: dict = {"type": "Feature", "geometry": _GEOM, "properties": props}
    if fid is not None:
        f["id"] = fid
    return f


def _plain_feature() -> dict:
    return {"type": "Feature", "geometry": _GEOM, "properties": {"label": "x"}}


def _create(conn, feature, *, coll: str = _COLL) -> str:
    row = conn.execute(
        "select ogc.feature_create(%s, %s, %s)",
        (_DS, coll, orjson.dumps(feature).decode()),
    ).fetchone()
    return str(row[0])


def _replace(conn, fid: str, feature) -> bool:
    row = conn.execute(
        "select ogc.feature_replace(%s, %s, %s, %s)",
        (_DS, _COLL, fid, orjson.dumps(feature).decode()),
    ).fetchone()
    return row[0]


def _update(conn, fid: str, feature) -> bool:
    row = conn.execute(
        "select ogc.feature_update(%s, %s, %s, %s)",
        (_DS, _COLL, fid, orjson.dumps(feature).decode()),
    ).fetchone()
    return row[0]


def _upsert(conn, feature) -> str:
    row = conn.execute(
        "select ogc.feature_upsert(%s, %s, %s)",
        (_DS, _COLL, orjson.dumps(feature).decode()),
    ).fetchone()
    return str(row[0])


def _fetch(conn, fid: str, *, coll: str = _COLL) -> dict | None:
    row = conn.execute(
        "select ogc.feature_item(%s, %s, %s::uuid)",
        (_DS, coll, fid),
    ).fetchone()
    return row[0] if row else None


def _oi_of(feature: dict) -> str | None:
    return feature["properties"]["identification"].get("testoi")


# ── Insert identity resolution ─────────────────────────────────────────────────


@dataclass(frozen=True)
class CreateCase:
    id: str
    fid: str | None  # value for GeoJSON feature.id
    testoi: str | None  # value for identification.testoi
    expected_id: str | None  # expected row id; None means server-minted
    expected_sqlstate: str | None  # None means success


_CREATE_CASES: list[CreateCase] = [
    CreateCase("feature-id-only", _A, None, _A, None),
    CreateCase("oi-path-only", None, _B, _B, None),
    CreateCase("both-equal", _u(0xC), _u(0xC), _u(0xC), None),
    CreateCase("both-different", _A, _B, None, "P0001"),
    CreateCase("neither", None, None, None, None),
    CreateCase("non-uuid-feature-id", "BANE-001", None, None, "22P02"),
    CreateCase("non-uuid-oi-path", None, "BANE-001", None, "22P02"),
]

_ACCEPTED = [c for c in _CREATE_CASES if c.expected_sqlstate is None]
_REJECTED = [c for c in _CREATE_CASES if c.expected_sqlstate is not None]


@pytest.mark.parametrize("case", _ACCEPTED, ids=[c.id for c in _ACCEPTED])
def test_create_accepted(oid_conn, case: CreateCase):
    """Accepted inserts are stored under the resolved id; OI is projected back on read."""
    new_id = _create(oid_conn, _feature(fid=case.fid, testoi=case.testoi))
    if case.expected_id is not None:
        assert new_id == case.expected_id
    got = _fetch(oid_conn, new_id)
    assert got is not None
    assert got["id"] == new_id
    assert _oi_of(got) == new_id


@pytest.mark.parametrize("case", _REJECTED, ids=[c.id for c in _REJECTED])
def test_create_rejected(oid_conn, case: CreateCase):
    """Invalid inserts are rejected with the declared SQLSTATE."""
    with pytest.raises(psycopg.Error) as exc:
        _create(oid_conn, _feature(fid=case.fid, testoi=case.testoi))
    assert exc.value.sqlstate == case.expected_sqlstate


# ── Upsert identity resolution ────────────────────────────────────────────────
#
# Same contract as create for accepting/rejecting, with one difference:
# absent identifier → P0001 rather than minting, because upsert needs a stable
# id to determine whether to insert or update.

_UPSERT_CASES: list[CreateCase] = [
    CreateCase("feature-id-only", _u(0xA0), None, _u(0xA0), None),
    CreateCase("oi-path-only", None, _u(0xB0), _u(0xB0), None),
    CreateCase("both-equal", _u(0xC0), _u(0xC0), _u(0xC0), None),
    CreateCase("both-different", _u(0xA0), _u(0xB0), None, "P0001"),
    CreateCase("neither", None, None, None, "P0001"),
    CreateCase("non-uuid-feature-id", "BANE-001", None, None, "22P02"),
    CreateCase("non-uuid-oi-path", None, "BANE-001", None, "22P02"),
]

_UPSERT_ACCEPTED = [c for c in _UPSERT_CASES if c.expected_sqlstate is None]
_UPSERT_REJECTED = [c for c in _UPSERT_CASES if c.expected_sqlstate is not None]


@pytest.mark.parametrize("case", _UPSERT_ACCEPTED, ids=[c.id for c in _UPSERT_ACCEPTED])
def test_upsert_accepted(oid_conn, case: CreateCase):
    """Accepted upserts are stored under the resolved id; OI is projected back on read."""
    new_id = _upsert(oid_conn, _feature(fid=case.fid, testoi=case.testoi))
    if case.expected_id is not None:
        assert new_id == case.expected_id
    got = _fetch(oid_conn, new_id)
    assert got is not None
    assert got["id"] == new_id
    assert _oi_of(got) == new_id


@pytest.mark.parametrize("case", _UPSERT_REJECTED, ids=[c.id for c in _UPSERT_REJECTED])
def test_upsert_rejected(oid_conn, case: CreateCase):
    """Invalid upserts are rejected with the declared SQLSTATE."""
    with pytest.raises(psycopg.Error) as exc:
        _upsert(oid_conn, _feature(fid=case.fid, testoi=case.testoi))
    assert exc.value.sqlstate == case.expected_sqlstate


def test_upsert_is_idempotent_on_matching_id(oid_conn):
    """A second upsert with the same id updates the row; the id is unchanged."""
    fid = _u(0xD0)
    id1 = _upsert(oid_conn, _feature(fid=fid))
    id2 = _upsert(oid_conn, _feature(fid=fid))
    assert id1 == id2 == fid


# ── Update identity guard ──────────────────────────────────────────────────────


def test_update_with_different_oi_is_rejected(oid_conn):
    """A patch carrying a different outward identifier is rejected P0001."""
    fid = _u(0xE0)
    _create(oid_conn, _feature(fid=fid))
    with pytest.raises(psycopg.Error) as exc:
        _update(oid_conn, fid, _feature(testoi=_u(0xE1)))
    assert exc.value.sqlstate == "P0001"


def test_update_with_same_oi_is_accepted(oid_conn):
    """A patch carrying the matching outward identifier is a valid round-trip."""
    fid = _u(0xF0)
    _create(oid_conn, _feature(fid=fid))
    assert _update(oid_conn, fid, _feature(testoi=fid)) is True


# ── Projection and addressability ─────────────────────────────────────────────────


def test_outward_identifier_is_projected_and_addressable(oid_conn):
    """OI equals feature.id on read; the feature is reachable by its OI value."""
    fid = _u(0x70)
    _create(oid_conn, _feature(fid=fid))
    got = _fetch(oid_conn, fid)
    assert got is not None
    assert got["id"] == fid
    assert _oi_of(got) == fid


# ── Replace identity guard ──────────────────────────────────────────────────────


def test_replace_with_different_oi_is_rejected(oid_conn):
    """A replace carrying a different outward identifier is rejected P0001."""
    fid = _u(0x80)
    _create(oid_conn, _feature(fid=fid))
    with pytest.raises(psycopg.Error) as exc:
        _replace(oid_conn, fid, _feature(testoi=_u(0x81)))
    assert exc.value.sqlstate == "P0001"


def test_replace_with_same_oi_is_accepted(oid_conn):
    """A replace carrying the matching outward identifier is a valid round-trip."""
    fid = _u(0x90)
    _create(oid_conn, _feature(fid=fid))
    assert _replace(oid_conn, fid, _feature(testoi=fid)) is True


# ── Two minted features must not collide (proves the old index is gone) ───────────


def test_two_features_without_identifier_both_succeed(oid_conn):
    """Minting two features must not collide; proves the old NULLS NOT DISTINCT index is gone."""
    id1 = _create(oid_conn, _feature())
    id2 = _create(oid_conn, _feature())
    assert id1 != id2


# ── Uniqueness via primary key ──────────────────────────────────────────────────


def test_duplicate_identifier_is_rejected(oid_conn):
    """Uniqueness is preserved by the primary key after the functional index is dropped."""
    fid = _u(0x11)
    _create(oid_conn, _feature(fid=fid))
    with pytest.raises(psycopg.Error) as exc:
        _create(oid_conn, _feature(fid=fid))
    assert exc.value.sqlstate == "23505"


# ── Collection without OI is unaffected ───────────────────────────────────────


def test_plain_collection_without_oi_is_unaffected(oid_conn):
    """The OI projection must not bleed into collections that declare no outward identifier."""
    new_id = _create(oid_conn, _plain_feature(), coll=_PLAIN)
    got = _fetch(oid_conn, new_id, coll=_PLAIN)
    assert got is not None
    assert got["id"] == new_id
    assert "identification" not in got["properties"]
