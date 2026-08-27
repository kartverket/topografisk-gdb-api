"""One easily-explainable end-to-end happy path.

Description -> schema (via the `db` fixture: apply-schema) -> serve (gateway) ->
HTTP CRUD roundtrip. If any seam is broken, this single readable test fails.
"""

from __future__ import annotations

import uuid
from http import HTTPStatus

import orjson
import psycopg
import pyproj
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

API = "/datasets/cadastre/ogc_api"
BYGNING_API = "/datasets/bygning/ogc_api"
PARCEL = {
    "type": "Feature",
    "geometry": {
        "type": "MultiPolygon",
        "coordinates": [[[[10, 55], [10, 56], [11, 56], [11, 55], [10, 55]]]],
    },
    "properties": {"label": "integration", "source": "test"},
}
# Self-intersecting (bowtie) polygon — ST_IsValid returns false.
_INVALID_GEOM = {
    "type": "MultiPolygon",
    "coordinates": [[[[0, 0], [1, 1], [0, 1], [1, 0], [0, 0]]]],
}

BYGNING = {
    "id": str(uuid.UUID(int=0xBB1)),
    "type": "Feature",
    "geometry": {
        "type": "MultiLineString",
        "coordinates": [
            [
                [522867.9097999996, 6857053.890000001, 302.19],
                [522874.4998000003, 6857056.890000001, 301.94],
                [522873.3398000002, 6857054.789999999, 301.81],
                [522868.7898000004, 6857052.760000002, 301.85],
                [522869.0697999997, 6857053.280000001, 301.85],
                [522867.9097999996, 6857053.890000001, 302.19],
            ]
        ],
    },
    "properties": {
        "lokalid": "building-integration-1",
        "identifikasjon_navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
        "oppdateringsdato": "2026-08-07T12:00:00Z",
        "datafangstdato": "2026-08-07T12:00:00Z",
        "objtype": "BygningBru",
        "source": "test",
    },
}

BYGNING_OMRADE = {
    "id": str(uuid.UUID(int=0xBB2)),
    "type": "Feature",
    "geometry": {
        "type": "MultiPolygon",
        "coordinates": [
            [
                [
                    [529540.2541, 6853079.3009, 495.652],
                    [529544.7306, 6853080.6285, 495.652],
                    [529546.4499, 6853074.8313, 495.652],
                    [529541.9734, 6853073.5036, 495.652],
                    [529540.2541, 6853079.3009, 495.652],
                ]
            ]
        ],
    },
    "properties": {
        "lokalid": "building-area-integration-1",
        "identifikasjon_navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
        "oppdateringsdato": "2026-08-07T12:00:00Z",
        "datafangstdato": "2026-08-07T12:00:00Z",
        "objtype": "AnnenBygning",
        "source": "test",
    },
}

BYGNING_SENTERLINJE = {
    "id": str(uuid.UUID(int=0xBB3)),
    "type": "Feature",
    "geometry": {
        "type": "MultiLineString",
        "coordinates": [
            [
                [517473.8998, 6846070.51, 450.46],
                [517471.5698, 6846072.11, 450.56],
            ]
        ],
    },
    "properties": {
        "lokalid": "building-centreline-integration-1",
        "identifikasjon_navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
        "oppdateringsdato": "2026-08-07T12:00:00Z",
        "datafangstdato": "2026-08-07T12:00:00Z",
        "objtype": "Hjelpelinje3D",
        "tredniva": "2",
        "source": "test",
    },
}

BYGNING_POSISJON = {
    "id": str(uuid.UUID(int=0xBB4)),
    "type": "Feature",
    "geometry": {
        "type": "Point",
        "coordinates": [529542.1498, 6853063.56, -99999.0],
    },
    "properties": {
        "lokalid": "building-position-integration-1",
        "identifikasjon_navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
        "oppdateringsdato": "2026-08-07T12:00:00Z",
        "datafangstdato": "2026-08-07T12:00:00Z",
        "objtype": "Bygning",
        "medium": "X",
        "bygningsnummer": 301583667,
        "bygningstype": 241,
        "bygningsstatus": "IG",
        "kommunenummer": "3437",
        "source": "test",
    },
}
# --------------------------------------------------------------------------
# Dummy dataset for outward_identifier tests
# --------------------------------------------------------------------------

_IDENT_DATASET = ResolvedDataset(
    name="test_ident",
    title="Test Identifikasjon",
    description="",
    collections=(
        ResolvedCollection(
            name="line",
            title="Line",
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
                        ResolvedField("versjonid", "text"),
                    ),
                ),
                ResolvedField("oppdateringsdato", "timestamptz", required=True),
            ),
            relationships=(),
            outward_identifier_path="identifikasjon.lokalid",
            server_managed_paths={
                "identifikasjon.versjonid": "timestamp_iso",
                "oppdateringsdato": "timestamp_iso",
            },
        ),
    ),
)

_IDENT_API = "/datasets/test_ident/ogc_api"
_IDENT_GEOM = {"type": "LineString", "coordinates": [[10, 55], [11, 56]]}


@pytest.fixture(scope="module")
def ident_client(db):
    conn = psycopg.connect(db)
    conn.autocommit = True
    conn.execute("drop schema if exists test_ident cascade")
    conn.autocommit = False
    plan = build_schema_plan(_IDENT_DATASET)
    _postgis.apply_tables(conn, plan)
    _schema_fns.apply_functions(conn, plan)
    conn.close()
    return TestClient(
        build_gateway(
            [_IDENT_DATASET],
            PygeoapiProvider(dsn=db),
            base_url="http://localhost:8000",
        )
    )


def test_description_to_api_crud_roundtrip(db, datasets):
    client = TestClient(
        build_gateway(
            datasets, PygeoapiProvider(dsn=db), base_url="http://localhost:8000"
        )
    )

    # 1. the dataset is discoverable
    assert "cadastre" in {d["id"] for d in client.get("/datasets").json()["datasets"]}

    # 2. create a parcel
    r = client.post(
        f"{API}/collections/parcels/items",
        content=orjson.dumps(PARCEL).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert r.status_code == HTTPStatus.CREATED
    fid = r.headers["Location"].rstrip("/").split("/")[-1]

    # 3. read it back
    assert (
        client.get(f"{API}/collections/parcels/items/{fid}?f=json").json()["id"] == fid
    )

    # 4. partial update
    client.patch(
        f"{API}/collections/parcels/items/{fid}",
        content=orjson.dumps({"properties": {"label": "updated"}}).decode(),
        headers={"content-type": "application/geo+json"},
    )

    # 5. it appears in the collection with the new value
    feats = client.get(f"{API}/collections/parcels/items?f=json").json()["features"]
    match = next(f for f in feats if f["id"] == fid)
    assert match["properties"]["label"] == "updated"

    # 6. delete -> gone
    assert (
        client.delete(f"{API}/collections/parcels/items/{fid}").status_code
        == HTTPStatus.OK
    )
    assert (
        client.get(f"{API}/collections/parcels/items/{fid}?f=json").status_code
        == HTTPStatus.NOT_FOUND
    )


def _client(db, datasets):
    return TestClient(
        build_gateway(
            datasets, PygeoapiProvider(dsn=db), base_url="http://localhost:8000"
        )
    )


def test_bygning_upsert_roundtrip(db, datasets):
    client = _client(db, datasets)
    first = client.post(
        f"{BYGNING_API}/collections/bygning/items:upsert",
        content=orjson.dumps(BYGNING).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert first.status_code == HTTPStatus.OK

    replaced = dict(BYGNING)
    replaced["properties"] = dict(BYGNING["properties"])
    replaced["properties"]["informasjon"] = "updated"
    second = client.post(
        f"{BYGNING_API}/collections/bygning/items:upsert",
        content=orjson.dumps(replaced).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert second.status_code == HTTPStatus.OK
    assert second.json()["id"] == first.json()["id"]

    item = client.get(
        f"{BYGNING_API}/collections/bygning/items/{first.json()['id']}?f=json"
    ).json()
    assert item["geometry"]["type"] == "MultiLineString"
    assert item["properties"]["informasjon"] == "updated"

    transformer = pyproj.Transformer.from_crs(5972, 4326, always_xy=True)
    lon, lat = transformer.transform(522867.9097999996, 6857053.890000001)
    listed = client.get(
        f"{BYGNING_API}/collections/bygning/items?"
        f"bbox={lon - 0.001},{lat - 0.001},{lon + 0.001},{lat + 0.001}&f=json"
    ).json()
    match = next(f for f in listed["features"] if f["id"] == first.json()["id"])
    listed_lon, listed_lat, listed_z = match["geometry"]["coordinates"][0][0]
    assert abs(listed_lon - lon) < 1e-6
    assert abs(listed_lat - lat) < 1e-6
    assert listed_z == 302.19


def test_bygning_batch_upsert_process_roundtrip(db, datasets):
    client = _client(db, datasets)

    second = dict(BYGNING)
    second["id"] = str(uuid.UUID(int=0xBB5))  # distinct id so two rows are created
    second["properties"] = dict(BYGNING["properties"])
    second["properties"]["lokalid"] = "building-integration-2"

    response = client.post(
        f"{BYGNING_API}/processes/upsert-batch/execution",
        content=orjson.dumps(
            {"inputs": {"collection": "bygning", "features": [BYGNING, second]}}
        ).decode(),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == HTTPStatus.OK
    result = response.json()
    assert len(result["features"]) == 2

    first_item = client.get(
        f"{BYGNING_API}/collections/bygning/items/{result['features'][0]['id']}?f=json"
    ).json()
    second_item = client.get(
        f"{BYGNING_API}/collections/bygning/items/{result['features'][1]['id']}?f=json"
    ).json()

    assert first_item["properties"]["lokalid"] == "building-integration-1"
    assert second_item["properties"]["lokalid"] == "building-integration-2"


def test_bygning_omrade_upsert_roundtrip(db, datasets):
    client = _client(db, datasets)

    first = client.post(
        f"{BYGNING_API}/collections/bygning_omrade/items:upsert",
        content=orjson.dumps(BYGNING_OMRADE).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert first.status_code == HTTPStatus.OK

    replaced = dict(BYGNING_OMRADE)
    replaced["properties"] = dict(BYGNING_OMRADE["properties"])
    replaced["properties"]["informasjon"] = "updated"
    second = client.post(
        f"{BYGNING_API}/collections/bygning_omrade/items:upsert",
        content=orjson.dumps(replaced).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert second.status_code == HTTPStatus.OK
    assert second.json()["id"] == first.json()["id"]

    item = client.get(
        f"{BYGNING_API}/collections/bygning_omrade/items/{first.json()['id']}?f=json"
    ).json()
    assert item["geometry"]["type"] == "MultiPolygon"
    assert item["properties"]["informasjon"] == "updated"


def test_bygning_senterlinje_upsert_roundtrip(db, datasets):
    client = _client(db, datasets)

    first = client.post(
        f"{BYGNING_API}/collections/bygning_senterlinje/items:upsert",
        content=orjson.dumps(BYGNING_SENTERLINJE).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert first.status_code == HTTPStatus.OK

    replaced = dict(BYGNING_SENTERLINJE)
    replaced["properties"] = dict(BYGNING_SENTERLINJE["properties"])
    replaced["properties"]["informasjon"] = "updated"
    second = client.post(
        f"{BYGNING_API}/collections/bygning_senterlinje/items:upsert",
        content=orjson.dumps(replaced).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert second.status_code == HTTPStatus.OK
    assert second.json()["id"] == first.json()["id"]

    item = client.get(
        f"{BYGNING_API}/collections/bygning_senterlinje/items/{first.json()['id']}?f=json"
    ).json()
    assert item["geometry"]["type"] == "MultiLineString"
    assert item["properties"]["informasjon"] == "updated"

    transformer = pyproj.Transformer.from_crs(5972, 4326, always_xy=True)
    lon, lat = transformer.transform(517473.8998, 6846070.51)
    listed = client.get(
        f"{BYGNING_API}/collections/bygning_senterlinje/items?"
        f"bbox={lon - 0.001},{lat - 0.001},{lon + 0.001},{lat + 0.001}&f=json"
    ).json()
    match = next(f for f in listed["features"] if f["id"] == first.json()["id"])
    listed_lon, listed_lat, listed_z = match["geometry"]["coordinates"][0][0]
    assert abs(listed_lon - lon) < 1e-6
    assert abs(listed_lat - lat) < 1e-6
    assert listed_z == 450.46


def test_bygning_posisjon_upsert_roundtrip(db, datasets):
    client = _client(db, datasets)

    first = client.post(
        f"{BYGNING_API}/collections/bygning_posisjon/items:upsert",
        content=orjson.dumps(BYGNING_POSISJON).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert first.status_code == HTTPStatus.OK

    replaced = dict(BYGNING_POSISJON)
    replaced["properties"] = dict(BYGNING_POSISJON["properties"])
    replaced["properties"]["informasjon"] = "updated"
    second = client.post(
        f"{BYGNING_API}/collections/bygning_posisjon/items:upsert",
        content=orjson.dumps(replaced).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert second.status_code == HTTPStatus.OK
    assert second.json()["id"] == first.json()["id"]

    item = client.get(
        f"{BYGNING_API}/collections/bygning_posisjon/items/{first.json()['id']}?f=json"
    ).json()
    assert item["geometry"]["type"] == "Point"
    assert item["properties"]["informasjon"] == "updated"

    transformer = pyproj.Transformer.from_crs(5972, 4326, always_xy=True)
    lon, lat = transformer.transform(529542.1498, 6853063.56)
    listed = client.get(
        f"{BYGNING_API}/collections/bygning_posisjon/items?"
        f"bbox={lon - 0.001},{lat - 0.001},{lon + 0.001},{lat + 0.001}&f=json"
    ).json()
    match = next(f for f in listed["features"] if f["id"] == first.json()["id"])
    listed_lon, listed_lat, listed_z = match["geometry"]["coordinates"]
    assert abs(listed_lon - lon) < 1e-6
    assert abs(listed_lat - lat) < 1e-6
    assert listed_z == -99999.0


def test_create_with_invalid_codelist_value_returns_422(db, datasets):
    """Pre-code suspect (end-to-end): a codelist violation in the write function
    must surface as HTTP 422, not 500, via the P0001 → ProviderValidationError path."""
    feature = {
        **PARCEL,
        "properties": {**PARCEL["properties"], "status": "not_a_real_status"},
    }
    r = _client(db, datasets).post(
        f"{API}/collections/parcels/items",
        content=orjson.dumps(feature).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_create_with_invalid_geometry_returns_422(db, datasets):
    """Pre-code suspect (end-to-end): a geometry that fails ST_IsValid must
    surface as HTTP 422 via the P0001 → ProviderValidationError path."""
    feature = {**PARCEL, "geometry": _INVALID_GEOM}
    r = _client(db, datasets).post(
        f"{API}/collections/parcels/items",
        content=orjson.dumps(feature).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert r.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


# --------------------------------------------------------------------------
# outward_identifier: strip on write, inject on read
# --------------------------------------------------------------------------


def test_client_uuid_lokalid_becomes_row_id_and_versjonid_is_server_managed(
    ident_client,
):
    """The client's UUID lokalid becomes the row id; versjonid is server-managed."""
    lok = str(uuid.uuid4())
    feature = {
        "type": "Feature",
        "geometry": _IDENT_GEOM,
        "properties": {
            "identifikasjon": {
                "lokalid": lok,
                "navnerom": "http://example.com",
                "versjonid": "client-supplied-version",
            }
        },
    }
    r = ident_client.post(
        f"{_IDENT_API}/collections/line/items",
        content=orjson.dumps(feature).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert r.status_code == HTTPStatus.CREATED
    fid = r.headers["Location"].rstrip("/").split("/")[-1]

    assert fid == lok  # row id equals the client's lokalid

    got = ident_client.get(f"{_IDENT_API}/collections/line/items/{fid}?f=json").json()
    ident = got["properties"]["identifikasjon"]
    assert ident["lokalid"] == lok  # projected from row id
    assert ident["versjonid"] != "client-supplied-version"  # server timestamp


def test_outward_identifier_injects_lokalid_and_versjonid_when_absent(ident_client):
    """When lokalid and versjonid are absent from the request, lokalid is
    injected from the row UUID and versjonid from the server clock on read."""
    feature = {
        "type": "Feature",
        "geometry": _IDENT_GEOM,
        "properties": {
            "identifikasjon": {"navnerom": "http://example.com"},
        },
    }
    r = ident_client.post(
        f"{_IDENT_API}/collections/line/items",
        content=orjson.dumps(feature).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert r.status_code == HTTPStatus.CREATED
    fid = r.headers["Location"].rstrip("/").split("/")[-1]

    got = ident_client.get(f"{_IDENT_API}/collections/line/items/{fid}?f=json").json()
    ident = got["properties"]["identifikasjon"]
    assert ident["lokalid"] == fid  # row UUID injected
    assert "versjonid" in ident  # server timestamp injected
