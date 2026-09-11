"""Contract tests for declared fields stored inside JSON objects."""

from __future__ import annotations

from dataclasses import dataclass

import orjson
import psycopg
import pytest
from conftest import _schema_conn

from geocomponents.descriptions.loader import resolve_dataset
from geocomponents.descriptions.models import Commons, DatasetDef
from geocomponents.schema.build import build_schema_plan

_DS = "test_nested_write"
_COLL = "items"
_GEOMETRY = {"type": "Point", "coordinates": [10.0, 60.0]}
_DATASET = resolve_dataset(
    DatasetDef.model_validate(
        {
            "name": _DS,
            "collections": [
                {
                    "name": _COLL,
                    "geometry": {"type": "Point", "srid": 4326},
                    "outward_identifier": "identification.localid",
                    "server_managed": {"identification.versionid": "timestamp_iso"},
                    "fields": [
                        {
                            "name": "identification",
                            "type": "object",
                            "required": True,
                            "fields": [
                                {"name": "localid", "type": "string", "required": True},
                                {
                                    "name": "namespace",
                                    "type": "string",
                                    "required": True,
                                },
                                {
                                    "name": "versionid",
                                    "type": "string",
                                    "required": True,
                                },
                            ],
                        },
                        {
                            "name": "quality",
                            "type": "object",
                            "required": True,
                            "fields": [
                                {
                                    "name": "method",
                                    "codelist": "method",
                                    "required": True,
                                },
                                {"name": "accuracy", "type": "integer"},
                            ],
                        },
                    ],
                }
            ],
            "codelists": [
                {"name": "method", "values": [{"code": "survey"}, {"code": "gps"}]}
            ],
        }
    ),
    Commons(),
)


@pytest.fixture(scope="module")
def nested_conn(db):
    with _schema_conn(db, build_schema_plan(_DATASET)) as conn:
        yield conn


def _feature(*, identification: dict | None = None, quality: dict | None = None):
    properties = {}
    if identification is not None:
        properties["identification"] = identification
    if quality is not None:
        properties["quality"] = quality
    return {"type": "Feature", "geometry": _GEOMETRY, "properties": properties}


def _valid_feature():
    return _feature(
        identification={"namespace": "example"},
        quality={"method": "survey", "accuracy": 2},
    )


def _create(conn, feature) -> str:
    return str(
        conn.execute(
            "select ogc.feature_create(%s, %s, %s)",
            (_DS, _COLL, orjson.dumps(feature).decode()),
        ).fetchone()[0]
    )


def _update(conn, fid: str, feature) -> bool:
    return conn.execute(
        "select ogc.feature_update(%s, %s, %s, %s)",
        (_DS, _COLL, fid, orjson.dumps(feature).decode()),
    ).fetchone()[0]


def _fetch(conn, fid: str) -> dict:
    return conn.execute(
        "select ogc.feature_item(%s, %s, %s::uuid)", (_DS, _COLL, fid)
    ).fetchone()[0]


@dataclass(frozen=True)
class RejectedObjectCase:
    id: str
    quality: object
    offending: str


_REJECTED_CASES = (
    RejectedObjectCase("object-given-string", "bad", "quality"),
    RejectedObjectCase("required-child-missing", {"accuracy": 2}, "quality.method"),
    RejectedObjectCase("required-child-null", {"method": None}, "quality.method"),
    RejectedObjectCase("bad-codelist", {"method": "other"}, "other"),
    RejectedObjectCase(
        "integer-given-string",
        {"method": "survey", "accuracy": "2"},
        "quality.accuracy",
    ),
    RejectedObjectCase(
        "undeclared-child", {"method": "survey", "mystery": "value"}, "mystery"
    ),
)


@pytest.mark.parametrize("case", _REJECTED_CASES, ids=lambda case: case.id)
def test_nested_object_rejections_name_the_offending_path_or_value(
    nested_conn, case: RejectedObjectCase
):
    with pytest.raises(psycopg.Error) as exc:
        _create(
            nested_conn,
            _feature(identification={"namespace": "example"}, quality=case.quality),
        )

    assert exc.value.sqlstate == "P0001"
    assert case.offending in str(exc.value)


def test_required_nested_children_present_are_accepted(nested_conn):
    fid = _create(nested_conn, _valid_feature())
    assert _fetch(nested_conn, fid)["properties"]["quality"] == {
        "method": "survey",
        "accuracy": 2,
    }


def test_server_contributions_satisfy_required_nested_children(nested_conn):
    fid = _create(nested_conn, _valid_feature())
    identification = _fetch(nested_conn, fid)["properties"]["identification"]

    assert identification["localid"] == fid
    assert identification["namespace"] == "example"
    assert identification["versionid"] is not None


def test_update_without_enclosing_object_leaves_stored_value_untouched(nested_conn):
    fid = _create(nested_conn, _valid_feature())
    before = _fetch(nested_conn, fid)["properties"]["quality"]

    assert _update(nested_conn, fid, {"type": "Feature", "properties": {}}) is True
    assert _fetch(nested_conn, fid)["properties"]["quality"] == before


def test_update_with_enclosing_object_validates_complete_replacement(nested_conn):
    fid = _create(nested_conn, _valid_feature())
    patch = {"type": "Feature", "properties": {"quality": {"accuracy": 3}}}

    with pytest.raises(psycopg.Error) as exc:
        _update(nested_conn, fid, patch)

    assert exc.value.sqlstate == "P0001"
    assert "quality.method" in str(exc.value)
