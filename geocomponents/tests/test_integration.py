"""One easily-explainable end-to-end happy path.

Description -> schema (via the `db` fixture: apply-schema) -> serve (gateway) ->
HTTP CRUD roundtrip. If any seam is broken, this single readable test fails.
"""

from __future__ import annotations

from http import HTTPStatus

import orjson
import pyproj
from starlette.testclient import TestClient

from geocomponents.api.pygeoapi_provider import PygeoapiProvider
from geocomponents.gateway.mounter import build_gateway

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

BYGNING = {
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


def test_bygning_upsert_roundtrip(db, datasets):
    client = TestClient(
        build_gateway(
            datasets, PygeoapiProvider(dsn=db), base_url="http://localhost:8000"
        )
    )

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


def test_bygning_omrade_upsert_roundtrip(db, datasets):
    client = TestClient(
        build_gateway(
            datasets, PygeoapiProvider(dsn=db), base_url="http://localhost:8000"
        )
    )

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
