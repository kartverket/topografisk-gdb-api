"""xfail tests pinning the known defects in _fn_upsert as of 2026-08-27.

Each test asserts the *intended* behaviour so it fails against the current
codebase.  When a defect is eventually fixed its test will xpass; strict=True
converts that to a pytest error — the signal to remove the xfail and promote
the test to a regular assertion.

See handovers/xfail_outward_identifier.md for the full context.
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


# --------------------------------------------------------------------------
# Defect 1: upsert without the outward-identifier sub-key is not rejected
# --------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=True,
    reason=(
        "upsert requires identifikasjon.lokalid as its conflict key "
        "(unique index, NULLS NOT DISTINCT); a feature without it is accepted today — "
        "the first absent-key insert occupies the one NULL slot, making the "
        "collection silently unaddressable for any subsequent upsert without lokalid"
    ),
)
def test_upsert_without_outward_identifier_sub_key_is_rejected(oi_client, conn):
    """Upsert requires identifikasjon.lokalid; omitting it must be rejected.

    The upsert conflict index is on identifikasjon.lokalid (NULLS NOT DISTINCT),
    so a feature without lokalid cannot be identified or de-duplicated.
    """
    with pytest.raises(psycopg.Error) as exc, conn.cursor() as cur:
        cur.execute(
            "select ogc.feature_upsert(%s, %s, %s)",
            ("test_oi", "spormidt", orjson.dumps(_feature()).decode()),
        )
    assert exc.value.sqlstate == "P0001"


# --------------------------------------------------------------------------
# Defect 2: a feature upserted by its outward identifier is not reachable by it
# --------------------------------------------------------------------------
@pytest.mark.xfail(
    strict=True,
    reason=(
        "ogc.feature_item signature is (dataset text, collection text, fid uuid); "
        "fetching by outward identifier value fails with 22P02 — "
        "invalid input syntax for type uuid"
    ),
)
def test_feature_upserted_by_outward_identifier_is_reachable_by_it(oi_client, conn):
    """A feature upserted by its outward identifier must be reachable by it.

    The upsert stores BANE-XF as the business key; fetching by BANE-XF via
    the HTTP dispatch layer must return 200 OK.  Today it fails with 22P02
    because ogc.feature_item accepts only a UUID.
    """
    with conn.cursor() as cur:
        cur.execute(
            "select ogc.feature_upsert(%s, %s, %s)",
            ("test_oi", "spormidt", orjson.dumps(_feature("BANE-XF")).decode()),
        )
    r = oi_client.get(f"{_API}/collections/spormidt/items/BANE-XF?f=json")
    assert r.status_code == HTTPStatus.OK
