"""Language-agnostic API contract: the HTTP OGC API surface.

Drives the mounted OGC API over HTTP (Starlette TestClient) and asserts the
observable behaviour — endpoints, per-collection capability (CRUD vs 405), bbox,
links, PATCH partial update, declared processes. No geocomponents internals are
touched beyond building the app the way ``serve`` does, so any server exposing
the same HTTP contract passes.

Generic checks are derived from the descriptions; a couple of fixed golden
assertions pin the examples.
"""

from __future__ import annotations

from http import HTTPStatus

import orjson
import pytest
from starlette.testclient import TestClient

from geocomponents.api.pygeoapi_provider import PygeoapiProvider
from geocomponents.gateway.mounter import build_gateway

BASE_URL = "http://localhost:8000"
_GEOM_MULTIPOLYGON = {
    "type": "MultiPolygon",
    "coordinates": [[[[10, 55], [10, 56], [11, 56], [11, 55], [10, 55]]]],
}


@pytest.fixture
def client(db, datasets):
    gw = build_gateway(datasets, PygeoapiProvider(dsn=db), base_url=BASE_URL)
    return TestClient(gw)


def _api(dataset_name: str) -> str:
    return f"/datasets/{dataset_name}/ogc_api"


# ===========================================================================
# Generic (derived from the descriptions)
# ===========================================================================
def test_landing_and_collections_listed_for_every_dataset(client, datasets):
    for d in datasets:
        api = _api(d.name)
        assert client.get(f"{api}/?f=json").status_code == HTTPStatus.OK
        listed = client.get(f"{api}/collections?f=json").json()["collections"]
        assert {c["id"] for c in listed} == {c.name for c in d.collections}


def test_html_landing_is_isolated_per_dataset(datasets):
    # Regression: pygeoapi memoizes the translated config in a process-global
    # cache keyed only by locale, which leaked the first dataset's HTML chrome
    # (links/title/static) into every dataset's page. Landing-page HTML needs no
    # DB, so this runs without one. (Vacuous with a single dataset.)
    client = TestClient(
        build_gateway(datasets, PygeoapiProvider(dsn="host=unused"), base_url=BASE_URL))
    for d in datasets:
        html = client.get(f"{_api(d.name)}/?f=html").text
        assert f"/datasets/{d.name}/ogc_api" in html
        for other in datasets:
            if other.name != d.name:
                assert f"/datasets/{other.name}/ogc_api" not in html


def test_items_return_featurecollection_with_links(client, datasets):
    for d in datasets:
        for coll in d.collections:
            r = client.get(f"{_api(d.name)}/collections/{coll.name}/items?f=json")
            assert r.status_code == HTTPStatus.OK
            fc = r.json()
            assert fc["type"] == "FeatureCollection"
            assert isinstance(fc["links"], list) and fc["links"]  # pygeoapi envelope


def test_capability_matches_feature_model(client, datasets):
    """Simple collections are writable; topology collections reject writes (405)."""
    empty = orjson.dumps({"type": "Feature", "geometry": _GEOM_MULTIPOLYGON,
                          "properties": {}}).decode()
    for d in datasets:
        for coll in d.collections:
            items = f"{_api(d.name)}/collections/{coll.name}/items"
            opts = client.options(items).headers.get("Allow", "")
            if coll.supports_crud:
                assert "POST" in opts
            else:
                assert "POST" not in opts
                # Every write verb is rejected with 405.
                assert client.post(items, content=empty,
                                   headers={"content-type": "application/geo+json"}
                                   ).status_code == HTTPStatus.METHOD_NOT_ALLOWED
                assert client.put(f"{items}/x", content=empty,
                                  headers={"content-type": "application/geo+json"}
                                  ).status_code == HTTPStatus.METHOD_NOT_ALLOWED
                assert client.patch(f"{items}/x", content=empty,
                                    headers={"content-type": "application/geo+json"}
                                    ).status_code == HTTPStatus.METHOD_NOT_ALLOWED
                assert client.delete(f"{items}/x").status_code == HTTPStatus.METHOD_NOT_ALLOWED
                # ...but reads still work.
                assert client.get(f"{items}?f=json").status_code == HTTPStatus.OK


def test_declared_processes_are_exactly_what_the_dataset_lists(client, datasets):
    for d in datasets:
        listed = client.get(f"{_api(d.name)}/processes?f=json").json()["processes"]
        assert {p["id"] for p in listed} == set(d.processes)


# ===========================================================================
# Fixed golden (the example dataset)
# ===========================================================================
def test_golden_cadastre_crud_and_patch_roundtrip(client):
    api = _api("cadastre")
    feat = {"type": "Feature", "geometry": _GEOM_MULTIPOLYGON,
            "properties": {"label": "A", "status": "active", "source": "golden"}}

    r = client.post(f"{api}/collections/parcels/items",
                    content=orjson.dumps(feat).decode(),
                    headers={"content-type": "application/geo+json"})
    assert r.status_code == HTTPStatus.CREATED
    fid = r.headers["Location"].rstrip("/").split("/")[-1]

    # PATCH changes only 'label'; 'source' is untouched.
    r = client.patch(f"{api}/collections/parcels/items/{fid}",
                     content=orjson.dumps({"properties": {"label": "B"}}).decode(),
                     headers={"content-type": "application/geo+json"})
    assert r.status_code == HTTPStatus.NO_CONTENT
    props = client.get(f"{api}/collections/parcels/items/{fid}?f=json").json()["properties"]
    assert props["label"] == "B"
    assert props["source"] == "golden"

    assert client.delete(f"{api}/collections/parcels/items/{fid}").status_code == HTTPStatus.OK
    assert client.get(
        f"{api}/collections/parcels/items/{fid}?f=json").status_code == HTTPStatus.NOT_FOUND


def test_golden_bbox_filter(client):
    api = _api("cadastre")
    feat = {"type": "Feature",
            "geometry": {"type": "MultiPolygon",
                         "coordinates": [[[[40, 10], [40, 11], [41, 11],
                                           [41, 10], [40, 10]]]]},
            "properties": {"label": "far", "source": "bbox"}}
    r = client.post(f"{api}/collections/parcels/items",
                    content=orjson.dumps(feat).decode(),
                    headers={"content-type": "application/geo+json"})
    fid = r.headers["Location"].rstrip("/").split("/")[-1]
    try:
        inside = client.get(
            f"{api}/collections/parcels/items?bbox=39,9,42,12&f=json").json()
        assert any(f["id"] == fid for f in inside["features"])
        outside = client.get(
            f"{api}/collections/parcels/items?bbox=0,0,1,1&f=json").json()
        assert all(f["id"] != fid for f in outside["features"])
    finally:
        client.delete(f"{api}/collections/parcels/items/{fid}")


def test_golden_conformance_includes_part4_even_though_dataset_has_topology(client):
    # cadastre mixes simple + topology; per OGC it may still declare Part 4,
    # because the topology collection is non-editable (returns 405).
    classes = client.get(f"{_api('cadastre')}/conformance?f=json").json()["conformsTo"]
    assert any("ogcapi-features-4" in u for u in classes)


def test_golden_process_execution_echoes(client):
    r = client.post(f"{_api('cadastre')}/processes/hello/execution",
                    content=orjson.dumps({"inputs": {"name": "world"}}).decode(),
                    headers={"content-type": "application/json"})
    assert r.status_code == HTTPStatus.OK
    assert "Dataset echoes: world" in r.text
