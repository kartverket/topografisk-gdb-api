"""One easily-explainable end-to-end happy path.

Description -> schema (via the `db` fixture: apply-schema) -> serve (gateway) ->
HTTP CRUD roundtrip. If any seam is broken, this single readable test fails.
"""

from __future__ import annotations

import orjson
from starlette.testclient import TestClient

from geocomp.api.pygeoapi_provider import PygeoapiProvider
from geocomp.gateway.mounter import build_gateway

API = "/datasets/cadastre/ogc_api"
PARCEL = {
    "type": "Feature",
    "geometry": {"type": "MultiPolygon",
                 "coordinates": [[[[10, 55], [10, 56], [11, 56], [11, 55], [10, 55]]]]},
    "properties": {"label": "integration", "source": "test"},
}


def test_description_to_api_crud_roundtrip(db, datasets):
    client = TestClient(build_gateway(datasets, PygeoapiProvider(dsn=db),
                                      base_url="http://localhost:8000"))

    # 1. the dataset is discoverable
    assert "cadastre" in {d["id"] for d in client.get("/datasets").json()["datasets"]}

    # 2. create a parcel
    r = client.post(f"{API}/collections/parcels/items",
                    content=orjson.dumps(PARCEL).decode(),
                    headers={"content-type": "application/geo+json"})
    assert r.status_code == 201
    fid = r.headers["Location"].rstrip("/").split("/")[-1]

    # 3. read it back
    assert client.get(
        f"{API}/collections/parcels/items/{fid}?f=json").json()["id"] == fid

    # 4. partial update
    client.patch(f"{API}/collections/parcels/items/{fid}",
                 content=orjson.dumps({"properties": {"label": "updated"}}).decode(),
                 headers={"content-type": "application/geo+json"})

    # 5. it appears in the collection with the new value
    feats = client.get(f"{API}/collections/parcels/items?f=json").json()["features"]
    match = next(f for f in feats if f["id"] == fid)
    assert match["properties"]["label"] == "updated"

    # 6. delete -> gone
    assert client.delete(f"{API}/collections/parcels/items/{fid}").status_code == 200
    assert client.get(
        f"{API}/collections/parcels/items/{fid}?f=json").status_code == 404
