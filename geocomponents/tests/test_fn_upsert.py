"""Tests upsert works as expected

Should be gathered with other tests in the future
"""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import orjson
import psycopg
import pytest
import yaml
from conftest import _schema_conn
from starlette.testclient import TestClient

from geocomponents.api.pygeoapi_provider import PygeoapiProvider
from geocomponents.descriptions.loader import resolve_dataset
from geocomponents.descriptions.models import Commons, DatasetDef
from geocomponents.gateway.mounter import build_gateway
from geocomponents.schema.build import build_schema_plan

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "oi_fixture.yaml"


def _load_dataset():
    raw = yaml.safe_load(_FIXTURE_PATH.read_text(encoding="utf-8"))
    return resolve_dataset(DatasetDef.model_validate(raw), Commons())


_DATASET = _load_dataset()

_API = "/datasets/test_oid/ogc_api"
_GEOM = {"type": "LineString", "coordinates": [[10.0, 55.0], [11.0, 56.0]]}


@pytest.fixture(scope="module")
def oi_client(db):
    with _schema_conn(db, build_schema_plan(_DATASET)):
        yield TestClient(
            build_gateway(
                [_DATASET],
                PygeoapiProvider(dsn=db),
                base_url="http://localhost:8000",
            )
        )


def _feature(testoi: str | None = None) -> dict:
    props: dict = {"identification": {}}
    if testoi is not None:
        props["identification"]["testoi"] = testoi
    return {"type": "Feature", "geometry": _GEOM, "properties": props}


def test_upsert_without_outward_identifier_sub_key_is_rejected(oi_client, conn):
    """Upsert requires identification.testoi; omitting it must be rejected.

    The outward identifier IS the row id.  Without it, upsert has no stable
    identity to match on and cannot be idempotent, so P0001 is raised.
    """
    with pytest.raises(psycopg.Error) as exc, conn.cursor() as cur:
        cur.execute(
            "select ogc.feature_upsert(%s, %s, %s)",
            ("test_oid", "with_oi", orjson.dumps(_feature()).decode()),
        )
    assert exc.value.sqlstate == "P0001"


# The outward identifier is now a UUID (it IS the row id).
_BANE_UUID = "ba0eba0e-ba0e-4ba0-8ba0-ba0eba0eba0e"


def test_feature_upserted_by_outward_identifier_is_reachable_by_it(oi_client, conn):
    """A feature upserted by its outward identifier is reachable by that value.

    The outward identifier is the row id (a UUID).  ogc.feature_item takes
    a UUID, so fetching by the OI value returns 200 OK.
    """
    with conn.cursor() as cur:
        cur.execute(
            "select ogc.feature_upsert(%s, %s, %s)",
            ("test_oid", "with_oi", orjson.dumps(_feature(_BANE_UUID)).decode()),
        )
    r = oi_client.get(f"{_API}/collections/with_oi/items/{_BANE_UUID}?f=json")
    assert r.status_code == HTTPStatus.OK
