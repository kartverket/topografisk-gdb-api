"""Tests upsert works as expected

Should be gathered with other tests in the future
"""

from __future__ import annotations

from http import HTTPStatus

import orjson
import psycopg
import pytest
from starlette.testclient import TestClient

from geocomponents.api.pygeoapi_provider import PygeoapiProvider
from geocomponents.descriptions.models import (
    ResolvedCollection,
    ResolvedDataset,
    ResolvedField,
)
from geocomponents.gateway.mounter import build_gateway
from geocomponents.schema import functions as _schema_fns
from geocomponents.schema import postgis as _postgis
from geocomponents.schema.build import build_schema_plan

# --------------------------------------------------------------------------
# Minimal dataset: client-supplied outward identifier (not server-managed).
#
# upsert_path == outward_identifier_path bypasses the UUID-injection path in
# build.py so the client's lokalid value is stored and returned unchanged.
# This reproduces the fkb_bane.spormidt scenario described in the handover.
# --------------------------------------------------------------------------
_DATASET = ResolvedDataset(
    name="test_oi",
    title="Outward Identifier Contract",
    description="",
    collections=(
        ResolvedCollection(
            name="spormidt",
            title="Spormidt",
            description="",
            feature_model="simple",
            geometry_type="LineString",
            srid=4326,
            fields=(
                ResolvedField(
                    "identifikasjon",
                    "jsonb",
                    required=True,
                    sub_fields=(
                        ResolvedField("lokalid", "text", required=True),
                        ResolvedField("navnerom", "text", required=True),
                    ),
                ),
            ),
            relationships=(),
            upsert_field="identifikasjon",
            upsert_path="identifikasjon.lokalid",
            outward_identifier_path="identifikasjon.lokalid",
        ),
    ),
)

_API = "/datasets/test_oi/ogc_api"
_GEOM = {"type": "LineString", "coordinates": [[10.0, 55.0], [11.0, 56.0]]}


@pytest.fixture(scope="module")
def oi_client(db):
    conn = psycopg.connect(db)
    conn.autocommit = True
    conn.execute("drop schema if exists test_oi cascade")
    conn.autocommit = False
    plan = build_schema_plan(_DATASET)
    _postgis.apply_tables(conn, plan)
    _schema_fns.apply_functions(conn, plan)
    conn.close()
    return TestClient(
        build_gateway(
            [_DATASET],
            PygeoapiProvider(dsn=db),
            base_url="http://localhost:8000",
        )
    )


def _feature(lokalid: str | None = None) -> dict:
    props: dict = {"identifikasjon": {"navnerom": "http://example.com"}}
    if lokalid is not None:
        props["identifikasjon"]["lokalid"] = lokalid
    return {"type": "Feature", "geometry": _GEOM, "properties": props}


def test_upsert_without_outward_identifier_sub_key_is_rejected(oi_client, conn):
    """Upsert requires identifikasjon.lokalid; omitting it must be rejected.

    The outward identifier IS the row id.  Without it, upsert has no stable
    identity to match on and cannot be idempotent, so P0001 is raised.
    """
    with pytest.raises(psycopg.Error) as exc, conn.cursor() as cur:
        cur.execute(
            "select ogc.feature_upsert(%s, %s, %s)",
            ("test_oi", "spormidt", orjson.dumps(_feature()).decode()),
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
            ("test_oi", "spormidt", orjson.dumps(_feature(_BANE_UUID)).decode()),
        )
    r = oi_client.get(f"{_API}/collections/spormidt/items/{_BANE_UUID}?f=json")
    assert r.status_code == HTTPStatus.OK
