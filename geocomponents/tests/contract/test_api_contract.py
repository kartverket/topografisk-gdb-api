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


@pytest.fixture
def offline_client(datasets):
    # The OpenAPI doc, the feature schema, collection links and parameter
    # rejection are all derived from the description and need no database.
    gw = build_gateway(datasets, PygeoapiProvider(dsn="host=unused"), base_url=BASE_URL)
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
        build_gateway(datasets, PygeoapiProvider(dsn="host=unused"), base_url=BASE_URL)
    )
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
    empty = orjson.dumps(
        {"type": "Feature", "geometry": _GEOM_MULTIPOLYGON, "properties": {}}
    ).decode()
    for d in datasets:
        for coll in d.collections:
            items = f"{_api(d.name)}/collections/{coll.name}/items"
            opts = client.options(items).headers.get("Allow", "")
            if coll.supports_crud:
                assert "POST" in opts
            else:
                assert "POST" not in opts
                # Every write verb is rejected with 405.
                assert (
                    client.post(
                        items,
                        content=empty,
                        headers={"content-type": "application/geo+json"},
                    ).status_code
                    == HTTPStatus.METHOD_NOT_ALLOWED
                )
                assert (
                    client.put(
                        f"{items}/x",
                        content=empty,
                        headers={"content-type": "application/geo+json"},
                    ).status_code
                    == HTTPStatus.METHOD_NOT_ALLOWED
                )
                assert (
                    client.patch(
                        f"{items}/x",
                        content=empty,
                        headers={"content-type": "application/geo+json"},
                    ).status_code
                    == HTTPStatus.METHOD_NOT_ALLOWED
                )
                assert (
                    client.delete(f"{items}/x").status_code
                    == HTTPStatus.METHOD_NOT_ALLOWED
                )
                # ...but reads still work.
                assert client.get(f"{items}?f=json").status_code == HTTPStatus.OK


def test_405_on_non_editable_collection_advertises_all_allowed_methods(
    client, datasets
):
    """RFC 9110 §15.5.6: a 405 must list every method the resource
    supports in Allow. Both /items and /items/{id} support GET, HEAD, OPTIONS
    regardless of editability."""
    empty = orjson.dumps(
        {"type": "Feature", "geometry": _GEOM_MULTIPOLYGON, "properties": {}}
    ).decode()
    for d in datasets:
        for coll in d.collections:
            if coll.supports_crud:
                continue  # editable collections don't produce the 405 we care about
            items = f"{_api(d.name)}/collections/{coll.name}/items"
            expected = {"GET", "HEAD", "OPTIONS"}
            # /items rejects POST for non-editable
            r = client.post(
                items,
                content=empty,
                headers={"content-type": "application/geo+json"},
            )
            assert r.status_code == HTTPStatus.METHOD_NOT_ALLOWED
            assert {
                v.strip() for v in r.headers.get("Allow", "").split(",")
            } == expected
            # /items/{id} rejects PUT for non-editable
            r = client.put(
                f"{items}/x",
                content=empty,
                headers={"content-type": "application/geo+json"},
            )
            assert r.status_code == HTTPStatus.METHOD_NOT_ALLOWED
            assert {
                v.strip() for v in r.headers.get("Allow", "").split(",")
            } == expected


def test_declared_processes_are_exactly_what_the_dataset_lists(client, datasets):
    for d in datasets:
        listed = client.get(f"{_api(d.name)}/processes?f=json").json()["processes"]
        assert {p["id"] for p in listed} == set(d.processes)


# ===========================================================================
# OpenAPI / interface honesty (no DB): the advertised surface matches reality
# ===========================================================================
def test_openapi_omits_unimplemented_job_management(offline_client, datasets):
    # Processes run synchronously with no job store; the async /jobs paths that
    # pygeoapi would advertise are pruned so nothing dangles.
    for d in datasets:
        oas = offline_client.get(f"{_api(d.name)}/openapi?f=json").json()
        assert not any(p.startswith("/jobs") for p in oas["paths"])


def test_openapi_post_items_documents_only_a_geojson_create(offline_client):
    # The create example must describe a GeoJSON Feature with the collection's
    # exact geometry — not an empty schema, and not the CQL2 query-by-POST body
    # (application/json + a 200 FeatureCollection) that pygeoapi bundles in.
    oas = offline_client.get(f"{_api('cadastre')}/openapi?f=json").json()
    post = oas["paths"]["/collections/parcels/items"]["post"]
    assert list(post["requestBody"]["content"]) == ["application/geo+json"]
    assert "200" not in post["responses"] and "201" in post["responses"]
    schema = post["requestBody"]["content"]["application/geo+json"]["schema"]
    assert schema["properties"]["type"]["enum"] == ["Feature"]
    assert schema["properties"]["geometry"]["properties"]["type"]["enum"] == [
        "MultiPolygon"
    ]
    # A complete, postable example: right geometry type *with* coordinates.
    example = schema["example"]
    assert example["geometry"]["type"] == "MultiPolygon"
    assert example["geometry"]["coordinates"]  # non-empty


def test_openapi_advertises_upsert_only_for_configured_collections(offline_client):
    bane_oas = offline_client.get(f"{_api('bane')}/openapi?f=json").json()
    assert "/collections/jernbaneplattformkant/items:upsert" in bane_oas["paths"]
    cadastre_oas = offline_client.get(f"{_api('cadastre')}/openapi?f=json").json()
    assert not any(path.endswith("items:upsert") for path in cadastre_oas["paths"])


def test_collection_schema_endpoint_describes_the_feature(offline_client, datasets):
    for d in datasets:
        for coll in d.collections:
            r = offline_client.get(f"{_api(d.name)}/collections/{coll.name}/schema")
            assert r.status_code == HTTPStatus.OK
            schema = r.json()
            assert schema["properties"]["type"]["enum"] == ["Feature"]
            assert schema["properties"]["geometry"]["properties"]["type"]["enum"] == [
                coll.geometry_type
            ]


def test_collections_do_not_advertise_the_deferred_queryables(offline_client, datasets):
    # queryables belongs with real filtering (deferred to the DB dispatch); the
    # schema link, now routed, stays.
    for d in datasets:
        for coll in d.collections:
            links = offline_client.get(
                f"{_api(d.name)}/collections/{coll.name}?f=json"
            ).json()["links"]
            rels = [ln["rel"] for ln in links]
            assert not any(r.rstrip("/").endswith("queryables") for r in rels)
            assert any(r.rstrip("/").endswith("schema") for r in rels)
            assert "items" in rels


def test_cql_filter_is_refused_until_the_db_supports_it(offline_client):
    # Better an honest 400 than silently returning unfiltered results.
    r = offline_client.get(
        f"{_api('cadastre')}/collections/parcels/items?filter=label='x'"
    )
    assert r.status_code == HTTPStatus.BAD_REQUEST


# ===========================================================================
# Fixed golden (the example dataset)
# ===========================================================================
def test_golden_cadastre_crud_and_patch_roundtrip(client):
    api = _api("cadastre")
    feat = {
        "type": "Feature",
        "geometry": _GEOM_MULTIPOLYGON,
        "properties": {"label": "A", "status": "active", "source": "golden"},
    }

    r = client.post(
        f"{api}/collections/parcels/items",
        content=orjson.dumps(feat).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert r.status_code == HTTPStatus.CREATED
    fid = r.headers["Location"].rstrip("/").split("/")[-1]

    # PATCH changes only 'label'; 'source' is untouched.
    r = client.patch(
        f"{api}/collections/parcels/items/{fid}",
        content=orjson.dumps({"properties": {"label": "B"}}).decode(),
        headers={"content-type": "application/geo+json"},
    )
    assert r.status_code == HTTPStatus.NO_CONTENT
    props = client.get(f"{api}/collections/parcels/items/{fid}?f=json").json()[
        "properties"
    ]
    assert props["label"] == "B"
    assert props["source"] == "golden"

    assert (
        client.delete(f"{api}/collections/parcels/items/{fid}").status_code
        == HTTPStatus.OK
    )
    assert (
        client.get(f"{api}/collections/parcels/items/{fid}?f=json").status_code
        == HTTPStatus.NOT_FOUND
    )


def test_golden_bbox_filter(client):
    api = _api("cadastre")
    feat = {
        "type": "Feature",
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [[[[40, 10], [40, 11], [41, 11], [41, 10], [40, 10]]]],
        },
        "properties": {"label": "far", "source": "bbox"},
    }
    r = client.post(
        f"{api}/collections/parcels/items",
        content=orjson.dumps(feat).decode(),
        headers={"content-type": "application/geo+json"},
    )
    fid = r.headers["Location"].rstrip("/").split("/")[-1]
    try:
        inside = client.get(
            f"{api}/collections/parcels/items?bbox=39,9,42,12&f=json"
        ).json()
        assert any(f["id"] == fid for f in inside["features"])
        outside = client.get(
            f"{api}/collections/parcels/items?bbox=0,0,1,1&f=json"
        ).json()
        assert all(f["id"] != fid for f in outside["features"])
    finally:
        client.delete(f"{api}/collections/parcels/items/{fid}")


def test_bane_upsert_is_idempotent_by_business_key(client):
    url = f"{_api('bane')}/collections/jernbaneplattformkant/items:upsert"
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "MultiLineString",
            "coordinates": [[[100000, 7000000], [100010, 7000010]]],
        },
        "properties": {
            "lokalid": "platform-1",
            "identifikasjon_navnerom": "test",
            "oppdateringsdato": "2026-08-05T12:00:00Z",
            "datafangstdato": "2026-08-05T12:00:00Z",
            "medium": "T",
            "informasjon": "first",
        },
    }
    first = client.post(
        url,
        content=orjson.dumps(feature),
        headers={"content-type": "application/geo+json"},
    )
    assert first.status_code == HTTPStatus.OK

    feature["properties"]["informasjon"] = "replaced"
    second = client.post(
        url,
        content=orjson.dumps(feature),
        headers={"content-type": "application/geo+json"},
    )
    assert second.status_code == HTTPStatus.OK
    assert second.json()["id"] == first.json()["id"]

    item = client.get(
        f"{_api('bane')}/collections/jernbaneplattformkant/items/"
        f"{first.json()['id']}?f=json"
    ).json()
    assert item["properties"]["informasjon"] == "replaced"


def test_golden_conformance_includes_part4_even_though_dataset_has_topology(client):
    # cadastre mixes simple + topology; per OGC it may still declare Part 4,
    # because the topology collection is non-editable (returns 405).
    classes = client.get(f"{_api('cadastre')}/conformance?f=json").json()["conformsTo"]
    assert any("ogcapi-features-4" in u for u in classes)


def test_golden_process_execution_echoes(client):
    r = client.post(
        f"{_api('cadastre')}/processes/hello/execution",
        content=orjson.dumps({"inputs": {"name": "world"}}).decode(),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == HTTPStatus.OK
    assert "Dataset echoes: world" in r.text


# ===========================================================================
# POST /items media-type discipline (Comment 6)
# ===========================================================================
def test_post_items_rejects_application_json_with_415(offline_client):
    """application/json on POST /items is the Part 3/5 query-by-POST body
    (CQL2). Query-by-POST isn't implemented; reject rather than misroute the
    body into create."""
    r = offline_client.post(
        f"{_api('cadastre')}/collections/parcels/items",
        content=orjson.dumps({"filter": "true"}).decode(),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    assert r.headers.get("Accept-Post") == "application/geo+json"


def test_post_items_rejects_unknown_content_type_with_415(offline_client):
    r = offline_client.post(
        f"{_api('cadastre')}/collections/parcels/items",
        content="plain text",
        headers={"content-type": "text/plain"},
    )
    assert r.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE


def test_post_items_accepts_geojson_with_charset_parameter(offline_client):
    """Guards against regressing the prefix-match to strict equality: real
    clients send ``application/geo+json; charset=utf-8``."""
    body = orjson.dumps(
        {"type": "Feature", "geometry": _GEOM_MULTIPOLYGON, "properties": {}}
    ).decode()
    r = offline_client.post(
        f"{_api('cadastre')}/collections/parcels/items",
        content=body,
        headers={"content-type": "application/geo+json; charset=utf-8"},
    )
    assert r.status_code != HTTPStatus.UNSUPPORTED_MEDIA_TYPE


def test_post_items_rejects_missing_content_type_with_415(offline_client):
    r = offline_client.post(
        f"{_api('cadastre')}/collections/parcels/items",
        content=b"",
    )
    assert r.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
