from __future__ import annotations

import json
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from gcimport.app import create_app
from gcimport.config import Settings
from gcimport.importer import prepare_document
from gcimport.profiles import ImportProfile
from gcimport.profiles.bygning import (
    _AREA_SOURCE_OBJTYPES as _BUILDING_AREA_SOURCE_OBJTYPES,
)
from gcimport.pubsub import RecordingImportEventPublisher

PLATFORM_UUID = "11111111-1111-4111-8111-111111111111"
TRACK_UUID = "22222222-2222-4222-8222-222222222222"


def _properties(**overrides: Any) -> dict[str, Any]:
    values = {
        "lokalid": "feature-1",
        "identifikasjon_navnerom": "test",
        "oppdateringsdato": "2026-01-01T00:00:00Z",
        "datafangstdato": "2025-01-01T00:00:00Z",
        "kvalitet_datafangstmetode": "fot",
        "medium": "T",
    }
    values.update(overrides)
    return values


def _feature(
    *,
    feature_type: str = "jernbaneplattformkant",
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "featureType": feature_type,
        "place": {
            "type": "MultiLineString",
            "coordinates": [[[10.7, 59.9], [10.8, 60.0]]],
        },
        "properties": properties or _properties(),
    }


def _document(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "coordRefSys": "EPSG:4326",
        "features": features,
    }


def _building_properties(**overrides: Any) -> dict[str, Any]:
    values = {
        "lokalid": "building-1",
        "identifikasjon_navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
        "oppdateringsdato": "2026-01-01T00:00:00Z",
        "datafangstdato": "2025-01-01T00:00:00Z",
    }
    values.update(overrides)
    return values


def _building_feature(
    *,
    feature_type: str = "bygning",
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "featureType": feature_type,
        "place": {
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
        "properties": properties or _building_properties(),
    }


def _building_geojson_feature() -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "OBJECTID": 1,
            "objtype": "BygningBru",
            "lokalid": "building-1",
            "datafangstdato": "2025-01-01T00:00:00Z",
            "oppdateringsdato": "2026-01-01T00:00:00Z",
            "navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
        },
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
    }


def _building_geojson_duplicate_segment() -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "OBJECTID": 2,
            "objtype": "Takkant",
            "lokalid": "building-duplicate-1",
            "datafangstdato": "2025-01-01T00:00:00Z",
            "oppdateringsdato": "2026-01-01T00:00:00Z",
            "navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
            "versjonid": "2026-01-01 00:00:00.000000000",
            "SHAPE_Length": 1.23,
        },
        "geometry": {
            "type": "MultiLineString",
            "coordinates": [
                [
                    [522867.9097999996, 6857053.890000001, 302.19],
                    [522874.4998000003, 6857056.890000001, 301.94],
                ]
            ],
        },
    }


def _building_geojson_duplicate_segment_2() -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "OBJECTID": 3,
            "objtype": "Takkant",
            "lokalid": "building-duplicate-1",
            "datafangstdato": "2025-01-01T00:00:00Z",
            "oppdateringsdato": "2026-01-01T00:00:00Z",
            "navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
            "versjonid": "2026-01-01 00:00:00.000000000",
            "SHAPE_Length": 4.56,
        },
        "geometry": {
            "type": "MultiLineString",
            "coordinates": [
                [
                    [522873.3398000002, 6857054.789999999, 301.81],
                    [522868.7898000004, 6857052.760000002, 301.85],
                    [522869.0697999997, 6857053.280000001, 301.85],
                ]
            ],
        },
    }


def _building_geojson_document(
    features: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::5972"},
        },
        "features": features or [_building_geojson_feature()],
    }


def _building_area_feature(
    *,
    feature_type: str = "bygning_omrade",
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "featureType": feature_type,
        "place": {
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
        "properties": properties or _building_properties(),
    }


def _building_area_geojson_feature(*, objtype: str = "AnnenBygning") -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "OBJECTID": 1,
            "objtype": objtype,
            "lokalid": "building-area-1",
            "datafangstdato": "2025-01-01T00:00:00Z",
            "oppdateringsdato": "2026-01-01T00:00:00Z",
            "navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
        },
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
    }


def _building_area_geojson_document(
    features: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::5972"},
        },
        "features": features or [_building_area_geojson_feature()],
    }


def _building_centerline_feature(
    *,
    feature_type: str = "bygning_senterlinje",
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "featureType": feature_type,
        "place": {
            "type": "MultiLineString",
            "coordinates": [
                [
                    [517473.8998, 6846070.51, 450.46],
                    [517471.5698, 6846072.11, 450.56],
                ]
            ],
        },
        "properties": properties
        or _building_properties(
            objtype="Hjelpelinje3D",
            tredniva="2",
        ),
    }


def _building_centerline_geojson_feature(
    *, objtype: str = "Hjelpelinje3D"
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "OBJECTID": 1,
            "objtype": objtype,
            "lokalid": "building-centreline-1",
            "datafangstdato": "2011-05-09T00:00:00Z",
            "oppdateringsdato": "2026-02-28T00:31:01Z",
            "verifiseringsdato": "2025-07-11T00:00:00Z",
            "navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
            "tredniva": "2",
        },
        "geometry": {
            "type": "MultiLineString",
            "coordinates": [
                [
                    [517473.8998, 6846070.51, 450.46],
                    [517471.5698, 6846072.11, 450.56],
                ]
            ],
        },
    }


def _building_centerline_geojson_document(
    features: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::5972"},
        },
        "features": features or [_building_centerline_geojson_feature()],
    }


def _building_position_feature(
    *,
    feature_type: str = "bygning_posisjon",
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "Feature",
        "featureType": feature_type,
        "place": {
            "type": "Point",
            "coordinates": [529542.1498, 6853063.56, -99999.0],
        },
        "properties": properties
        or _building_properties(
            medium="X",
            bygningsnummer=301583667,
            bygningstype=241,
            bygningsstatus="IG",
            kommunenummer="3437",
        ),
    }


def _building_position_geojson_feature(*, objtype: str = "Bygning") -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {
            "OBJECTID": 1,
            "objtype": objtype,
            "lokalid": "building-position-1",
            "datafangstdato": "2026-03-03T00:00:00Z",
            "oppdateringsdato": "2026-03-05T00:31:07Z",
            "navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
            "medium": "X",
            "bygningsnummer": 301583667,
            "bygningstype": 241,
            "bygningsstatus": "IG",
            "kommunenummer": "3437",
        },
        "geometry": {
            "type": "Point",
            "coordinates": [529542.1498, 6853063.56, -99999.0],
        },
    }


def _building_position_geojson_document(
    features: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::5972"},
        },
        "features": features or [_building_position_geojson_feature()],
    }


def _post(client: TestClient, document: Any, *, profile: str) -> httpx2.Response:
    return client.post(
        f"/imports?profile={profile}",
        files={"file": ("bane.json", json.dumps(document), "application/json")},
    )


def _post_geojson(
    client: TestClient,
    document: Any,
    *,
    profile: str,
    filename: str = "source.geojson",
) -> httpx2.Response:
    return client.post(
        f"/imports?profile={profile}",
        files={"file": (filename, json.dumps(document), "application/geo+json")},
    )


def _test_client(
    handler: httpx2.MockTransport,
    *,
    max_upload_bytes: int = 100_000,
    upsert_batch_size: int = 250,
    event_publisher: RecordingImportEventPublisher | None = None,
) -> TestClient:
    upstream_client = httpx2.AsyncClient(transport=handler)
    app = create_app(
        settings=_settings(
            geocomponents_api_url="https://bane.example",
            max_upload_bytes=max_upload_bytes,
            upsert_batch_size=upsert_batch_size,
        ),
        client=upstream_client,
        event_publisher=event_publisher,
    )
    return TestClient(app)


def _settings(**overrides: Any) -> Settings:
    return Settings(redis_url="redis://redis:6379/0", **overrides)


def test_import_publishes_start_batch_and_success_events() -> None:
    publisher = RecordingImportEventPublisher()

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/processes/upsert-batch/execution")
        return httpx2.Response(
            200,
            json={
                "collection": "jernbaneplattformkant",
                "total": 2,
                "features": [
                    {"id": PLATFORM_UUID},
                    {"id": TRACK_UUID},
                ],
            },
        )

    first = _feature(properties=_properties(lokalid="feature-1"))
    second = _feature(properties=_properties(lokalid="feature-2"))

    with _test_client(
        httpx2.MockTransport(handler),
        upsert_batch_size=2,
        event_publisher=publisher,
    ) as client:
        response = _post(client, _document([first, second]), profile="fkb_bane")

    assert response.status_code == 200
    assert [event["event"] for event in publisher.events] == [
        "import.started",
        "import.parsed",
        "import.batch.succeeded",
        "import.completed.succeeded",
    ]
    assert all(event["profile"] == "fkb_bane" for event in publisher.events)
    assert publisher.events[1]["total_features"] == 2
    assert publisher.events[2]["batch_size"] == 2
    assert publisher.events[3]["imported_features"] == 2
    assert len({event["import_id"] for event in publisher.events}) == 1


def test_import_publishes_parse_failure_event() -> None:
    publisher = RecordingImportEventPublisher()

    with _test_client(
        httpx2.MockTransport(lambda _request: httpx2.Response(204)),
        event_publisher=publisher,
    ) as client:
        response = client.post(
            "/imports?profile=fkb_bane",
            files={"file": ("broken.json", "{", "application/json")},
        )

    assert response.status_code == 400
    assert [event["event"] for event in publisher.events] == [
        "import.started",
        "import.completed.failed",
    ]
    assert publisher.events[1]["phase"] == "parsing"


def test_import_publishes_batch_and_completion_failures() -> None:
    publisher = RecordingImportEventPublisher()

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500)

    first = _feature(properties=_properties(lokalid="feature-1"))
    second = _feature(properties=_properties(lokalid="feature-2"))

    with _test_client(
        httpx2.MockTransport(handler),
        upsert_batch_size=2,
        event_publisher=publisher,
    ) as client:
        response = _post(client, _document([first, second]), profile="fkb_bane")

    assert response.status_code == 502
    assert [event["event"] for event in publisher.events] == [
        "import.started",
        "import.parsed",
        "import.batch.failed",
        "import.completed.failed",
    ]
    assert publisher.events[2]["reason"] == "upstream returned HTTP 500"
    assert publisher.events[3]["reason"] == "upstream returned HTTP 500"


def test_import_uses_caller_supplied_import_id() -> None:
    publisher = RecordingImportEventPublisher()

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith(
            "/collections/jernbaneplattformkant/items:upsert"
        )
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    feature = _feature(properties=_properties(lokalid="feature-1"))

    with _test_client(
        httpx2.MockTransport(handler),
        event_publisher=publisher,
    ) as client:
        response = client.post(
            "/imports?profile=fkb_bane",
            headers={"X-Import-Id": "run-123"},
            files={
                "file": (
                    "source.json",
                    json.dumps(_document([feature])),
                    "application/json",
                )
            },
        )

    assert response.status_code == 200
    assert {event["import_id"] for event in publisher.events} == {"run-123"}


def test_imports_preflight_allows_any_origin() -> None:
    with _test_client(
        httpx2.MockTransport(lambda request: httpx2.Response(200))
    ) as client:
        response = client.options(
            "/imports",
            headers={
                "origin": "https://example.no",
                "access-control-request-method": "POST",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_imports_place_and_fallback_geometry() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        identifier = (
            TRACK_UUID
            if request.url.path.endswith("/spormidt/items:upsert")
            else PLATFORM_UUID
        )
        return httpx2.Response(200, json={"id": identifier})

    first = _feature(feature_type="JERNBANEPLATTFORMKANT")
    first["geometry"] = {"type": "Point", "coordinates": [0, 0]}
    second = _feature(
        feature_type="SporMidt",
        properties=_properties(
            lokalid="feature-2",
            jernbanetype="J",
            hoydereferanse="NN2000",
        ),
    )
    second.pop("place")
    second["geometry"] = {
        "type": "LineString",
        "coordinates": [[10.7, 59.9], [10.8, 60.0]],
    }

    with _test_client(httpx2.MockTransport(handler)) as client:
        response = _post(client, _document([first, second]), profile="fkb_bane")

    assert response.status_code == 200
    assert response.json() == {
        "total": 2,
        "features": [
            {"collection": "jernbaneplattformkant", "id": PLATFORM_UUID},
            {"collection": "spormidt", "id": TRACK_UUID},
        ],
    }
    assert [request.url.path for request in requests] == [
        "/datasets/fkb_bane/ogc_api/collections/jernbaneplattformkant/items:upsert",
        "/datasets/fkb_bane/ogc_api/collections/spormidt/items:upsert",
    ]
    for request in requests:
        assert request.headers["content-type"] == "application/geo+json"
        payload = json.loads(request.content)
        assert payload["type"] == "Feature"
        assert payload["geometry"]["type"] == "MultiLineString"
        assert payload["geometry"]["coordinates"][0][0] != [10.7, 59.9]


def test_retry_returns_the_same_upstream_uuid() -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    with _test_client(httpx2.MockTransport(handler)) as client:
        first = _post(client, _document([_feature()]), profile="fkb_bane")
        retry = _post(client, _document([_feature()]), profile="fkb_bane")

    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    assert first.json()["features"][0]["id"] == PLATFORM_UUID
    assert calls == 2


def test_imports_batch_same_collection_features() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        assert request.url.path.endswith("/processes/upsert-batch/execution")
        payload = json.loads(request.content)
        assert payload["inputs"]["collection"] == "jernbaneplattformkant"
        assert len(payload["inputs"]["features"]) == 2
        return httpx2.Response(
            200,
            json={
                "collection": "jernbaneplattformkant",
                "total": 2,
                "features": [{"id": PLATFORM_UUID}, {"id": TRACK_UUID}],
            },
        )

    second = _feature(
        properties=_properties(
            lokalid="feature-2",
            identifikasjon_navnerom="test-2",
        )
    )

    with _test_client(httpx2.MockTransport(handler)) as client:
        response = _post(
            client,
            _document([_feature(), second]),
            profile="fkb_bane",
        )

    assert response.status_code == 200
    assert response.json() == {
        "total": 2,
        "features": [
            {"collection": "jernbaneplattformkant", "id": PLATFORM_UUID},
            {"collection": "jernbaneplattformkant", "id": TRACK_UUID},
        ],
    }
    assert [request.url.path for request in requests] == [
        "/datasets/fkb_bane/ogc_api/processes/upsert-batch/execution"
    ]


def test_imports_falls_back_when_batch_route_is_unavailable() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        if request.url.path.endswith("/processes/upsert-batch/execution"):
            return httpx2.Response(404)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    second = _feature(
        properties=_properties(
            lokalid="feature-2",
            identifikasjon_navnerom="test-2",
        )
    )

    with _test_client(httpx2.MockTransport(handler)) as client:
        response = _post(
            client,
            _document([_feature(), second]),
            profile="fkb_bane",
        )

    assert response.status_code == 200
    assert response.json() == {
        "total": 2,
        "features": [
            {"collection": "jernbaneplattformkant", "id": PLATFORM_UUID},
            {"collection": "jernbaneplattformkant", "id": PLATFORM_UUID},
        ],
    }
    assert [request.url.path for request in requests] == [
        "/datasets/fkb_bane/ogc_api/processes/upsert-batch/execution",
        "/datasets/fkb_bane/ogc_api/collections/jernbaneplattformkant/items:upsert",
        "/datasets/fkb_bane/ogc_api/collections/jernbaneplattformkant/items:upsert",
    ]


def test_imports_bane_linestring_place_for_compatibility() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    feature = _feature()
    feature["place"] = {
        "type": "LineString",
        "coordinates": [[10.7, 59.9], [10.8, 60.0]],
    }

    with _test_client(httpx2.MockTransport(handler)) as client:
        response = _post(client, _document([feature]), profile="fkb_bane")

    assert response.status_code == 200
    payload = json.loads(requests[0].content)
    assert payload["geometry"]["type"] == "MultiLineString"
    assert payload["geometry"]["coordinates"][0][0][:2] != [10.7, 59.9]


def test_imports_fkb_bane_nested_upstream_properties() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    feature = _feature(
        properties=_properties(
            identifikasjon_versjonid="2026-01-02T00:00:00Z",
            kvalitet_noyaktighet=10,
        )
    )

    with _test_client(httpx2.MockTransport(handler)) as client:
        response = _post(client, _document([feature]), profile="fkb_bane")

    assert response.status_code == 200
    payload = json.loads(requests[0].content)
    assert payload["properties"]["identifikasjon"] == {
        "lokalid": "feature-1",
        "navnerom": "test",
        "versjonid": "2026-01-02T00:00:00Z",
    }
    assert payload["properties"]["kvalitet"] == {
        "datafangstmetode": "fot",
        "noyaktighet": 10,
    }


def test_dataset_rules_are_supplied_by_profile() -> None:
    profile = ImportProfile(
        name="roads",
        title="Roads",
        dataset_api_path="/datasets/roads/ogc_api",
        target_crs="EPSG:4326",
        geometry_type="LineString",
        collections={"road": "roads"},
        required_fields={"roads": frozenset({"road_id", "name"})},
        identity_fields=("road_id",),
    )
    document = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "featureType": "ROAD",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[10.7, 59.9], [10.8, 60.0]],
                },
                "properties": {"road_id": "r1", "name": "Main road"},
            }
        ],
    }

    prepared = prepare_document(document, profile)

    assert prepared[0].collection == "roads"
    assert prepared[0].feature_id == "r1"


def test_imports_built_in_bygning_profile_with_multilinestring() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    upstream_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        settings=_settings(geocomponents_api_url="https://bygning.example"),
        client=upstream_client,
    )

    with TestClient(app) as client:
        response = _post(
            client,
            {
                "type": "FeatureCollection",
                "coordRefSys": "EPSG:5972",
                "features": [_building_feature()],
            },
            profile="bygning",
        )

    assert response.status_code == 200
    assert response.json() == {
        "total": 1,
        "features": [{"collection": "bygning", "id": PLATFORM_UUID}],
    }
    assert [request.url.path for request in requests] == [
        "/datasets/bygning/ogc_api/collections/bygning/items:upsert"
    ]
    payload = json.loads(requests[0].content)
    assert payload["geometry"]["type"] == "MultiLineString"


def test_imports_built_in_bygning_omrade_profile_with_multipolygon() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    upstream_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        settings=_settings(geocomponents_api_url="https://bygning.example"),
        client=upstream_client,
    )

    with TestClient(app) as client:
        response = _post(
            client,
            {
                "type": "FeatureCollection",
                "coordRefSys": "EPSG:5972",
                "features": [_building_area_feature()],
            },
            profile="bygning",
        )

    assert response.status_code == 200
    assert response.json() == {
        "total": 1,
        "features": [{"collection": "bygning_omrade", "id": PLATFORM_UUID}],
    }
    assert [request.url.path for request in requests] == [
        "/datasets/bygning/ogc_api/collections/bygning_omrade/items:upsert"
    ]
    payload = json.loads(requests[0].content)
    assert payload["geometry"]["type"] == "MultiPolygon"


def test_imports_built_in_bygning_senterlinje_profile_with_multilinestring() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    upstream_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        settings=_settings(geocomponents_api_url="https://bygning.example"),
        client=upstream_client,
    )

    with TestClient(app) as client:
        response = _post(
            client,
            {
                "type": "FeatureCollection",
                "coordRefSys": "EPSG:5972",
                "features": [_building_centerline_feature()],
            },
            profile="bygning",
        )

    assert response.status_code == 200
    assert response.json() == {
        "total": 1,
        "features": [{"collection": "bygning_senterlinje", "id": PLATFORM_UUID}],
    }
    assert [request.url.path for request in requests] == [
        "/datasets/bygning/ogc_api/collections/bygning_senterlinje/items:upsert"
    ]
    payload = json.loads(requests[0].content)
    assert payload["geometry"]["type"] == "MultiLineString"


def test_imports_built_in_bygning_position_profile_with_point() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    upstream_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        settings=_settings(geocomponents_api_url="https://bygning.example"),
        client=upstream_client,
    )

    with TestClient(app) as client:
        response = _post(
            client,
            {
                "type": "FeatureCollection",
                "coordRefSys": "EPSG:5972",
                "features": [_building_position_feature()],
            },
            profile="bygning",
        )

    assert response.status_code == 200
    assert response.json() == {
        "total": 1,
        "features": [{"collection": "bygning_posisjon", "id": PLATFORM_UUID}],
    }
    assert [request.url.path for request in requests] == [
        "/datasets/bygning/ogc_api/collections/bygning_posisjon/items:upsert"
    ]
    payload = json.loads(requests[0].content)
    assert payload["geometry"]["type"] == "Point"


def test_rejects_missing_profile_query_parameter() -> None:
    with _test_client(
        httpx2.MockTransport(lambda _request: httpx2.Response(204))
    ) as client:
        response = client.post(
            "/imports",
            files={
                "file": (
                    "bane.json",
                    json.dumps(_document([_feature()])),
                    "application/json",
                )
            },
        )

    assert response.status_code == 422


def test_request_profile_selects_bygning_target_dataset() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    upstream_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        settings=_settings(geocomponents_api_url="https://shared.example"),
        client=upstream_client,
    )

    with TestClient(app) as client:
        response = client.post(
            "/imports?profile=bygning",
            files={
                "file": (
                    "source.geojson",
                    json.dumps(_building_geojson_document()),
                    "application/geo+json",
                )
            },
        )

    assert response.status_code == 200
    assert [request.url.path for request in requests] == [
        "/datasets/bygning/ogc_api/collections/bygning/items:upsert"
    ]


@pytest.mark.parametrize("objtype", ("AnnenBygning", "Bygning", "Takoverbygg"))
def test_request_profile_can_import_bygning_area_geojson_through_bygning_profile(
    objtype: str,
) -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    upstream_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        settings=_settings(geocomponents_api_url="https://shared.example"),
        client=upstream_client,
    )

    with TestClient(app) as client:
        response = client.post(
            "/imports?profile=bygning",
            files={
                "file": (
                    "source.geojson",
                    json.dumps(
                        _building_area_geojson_document(
                            [_building_area_geojson_feature(objtype=objtype)]
                        )
                    ),
                    "application/geo+json",
                )
            },
        )

    assert response.status_code == 200
    assert [request.url.path for request in requests] == [
        "/datasets/bygning/ogc_api/collections/bygning_omrade/items:upsert"
    ]


def test_request_profile_can_import_bygning_position_geojson_through_bygning_profile() -> (
    None
):
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    upstream_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        settings=_settings(geocomponents_api_url="https://shared.example"),
        client=upstream_client,
    )

    with TestClient(app) as client:
        response = client.post(
            "/imports?profile=bygning",
            files={
                "file": (
                    "source.geojson",
                    json.dumps(_building_position_geojson_document()),
                    "application/geo+json",
                )
            },
        )

    assert response.status_code == 200
    assert [request.url.path for request in requests] == [
        "/datasets/bygning/ogc_api/collections/bygning_posisjon/items:upsert"
    ]


def test_request_profile_can_import_bygning_senterlinje_geojson_through_bygning_profile() -> (
    None
):
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    upstream_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        settings=_settings(geocomponents_api_url="https://shared.example"),
        client=upstream_client,
    )

    with TestClient(app) as client:
        response = client.post(
            "/imports?profile=bygning",
            files={
                "file": (
                    "source.geojson",
                    json.dumps(_building_centerline_geojson_document()),
                    "application/geo+json",
                )
            },
        )

    assert response.status_code == 200
    assert [request.url.path for request in requests] == [
        "/datasets/bygning/ogc_api/collections/bygning_senterlinje/items:upsert"
    ]


def test_request_profile_can_import_mixed_bygning_geojson() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    upstream_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        settings=_settings(geocomponents_api_url="https://shared.example"),
        client=upstream_client,
    )

    with TestClient(app) as client:
        response = client.post(
            "/imports?profile=bygning",
            files={
                "file": (
                    "source.geojson",
                    json.dumps(
                        _building_area_geojson_document(
                            [
                                _building_geojson_feature(),
                                _building_area_geojson_feature(),
                            ]
                        )
                    ),
                    "application/geo+json",
                )
            },
        )

    assert response.status_code == 200
    assert [request.url.path for request in requests] == [
        "/datasets/bygning/ogc_api/collections/bygning/items:upsert",
        "/datasets/bygning/ogc_api/collections/bygning_omrade/items:upsert",
    ]


def test_rejects_unknown_request_profile() -> None:
    with _test_client(
        httpx2.MockTransport(lambda _request: httpx2.Response(204))
    ) as client:
        response = client.post(
            "/imports?profile=unknown",
            files={
                "file": (
                    "bane.json",
                    json.dumps(_document([_feature()])),
                    "application/json",
                )
            },
        )

    assert response.status_code == 400
    assert "profile must be one of" in response.json()["detail"]


def test_rejects_legacy_bygning_omrade_request_profile() -> None:
    with _test_client(
        httpx2.MockTransport(lambda _request: httpx2.Response(204))
    ) as client:
        response = client.post(
            "/imports?profile=bygning_omrade",
            files={
                "file": (
                    "source.geojson",
                    json.dumps(_building_area_geojson_document()),
                    "application/geo+json",
                )
            },
        )

    assert response.status_code == 400
    assert "profile must be one of" in response.json()["detail"]


def test_imports_bygning_geojson_without_falling_back_to_bane() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    upstream_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        settings=_settings(geocomponents_api_url="https://bygning.example"),
        client=upstream_client,
    )

    with TestClient(app) as client:
        response = _post_geojson(
            client,
            _building_geojson_document(),
            profile="bygning",
        )

    assert response.status_code == 200
    assert [request.url.path for request in requests] == [
        "/datasets/bygning/ogc_api/collections/bygning/items:upsert"
    ]
    payload = json.loads(requests[0].content)
    assert payload["geometry"]["type"] == "MultiLineString"


def test_imports_bygning_omrade_geojson_without_falling_back_to_bane() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    upstream_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        settings=_settings(geocomponents_api_url="https://bygning.example"),
        client=upstream_client,
    )

    with TestClient(app) as client:
        response = _post_geojson(
            client,
            _building_area_geojson_document(),
            profile="bygning",
        )

    assert response.status_code == 200
    assert [request.url.path for request in requests] == [
        "/datasets/bygning/ogc_api/collections/bygning_omrade/items:upsert"
    ]
    payload = json.loads(requests[0].content)
    assert payload["geometry"]["type"] == "MultiPolygon"


def test_bygning_profile_tracks_scanned_area_geojson_objtypes() -> None:
    assert tuple(_BUILDING_AREA_SOURCE_OBJTYPES) == (
        "annenbygning",
        "bygning",
        "takoverbygg",
    )


def test_merges_duplicate_bygning_segments_with_same_business_key() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": PLATFORM_UUID})

    upstream_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        settings=_settings(geocomponents_api_url="https://bygning.example"),
        client=upstream_client,
    )

    with TestClient(app) as client:
        response = _post_geojson(
            client,
            _building_geojson_document(
                [
                    _building_geojson_duplicate_segment(),
                    _building_geojson_duplicate_segment_2(),
                ]
            ),
            profile="bygning",
        )

    assert response.status_code == 200
    assert response.json() == {
        "total": 1,
        "features": [{"collection": "bygning", "id": PLATFORM_UUID}],
    }
    assert len(requests) == 1
    payload = json.loads(requests[0].content)
    assert payload["geometry"]["type"] == "MultiLineString"
    assert len(payload["geometry"]["coordinates"]) == 2


@pytest.mark.parametrize(
    ("mutate", "expected_error"),
    [
        (
            lambda feature: feature.update(featureType="unknown"),
            "featureType must be",
        ),
        (
            lambda feature: feature["properties"].pop("medium"),
            "missing required properties: medium",
        ),
        (
            lambda feature: feature["place"].update(
                type="Polygon",
                coordinates=[],
            ),
            "geometry must be a MultiLineString",
        ),
    ],
)
def test_validation_happens_before_upstream_calls(
    mutate: Any,
    expected_error: str,
) -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(204)

    valid = _feature()
    invalid = _feature(properties=_properties(lokalid="feature-2"))
    mutate(invalid)

    with _test_client(httpx2.MockTransport(handler)) as client:
        response = _post(client, _document([valid, invalid]), profile="fkb_bane")

    assert response.status_code == 422
    assert expected_error in " ".join(response.json()["detail"]["errors"])
    assert calls == 0


def test_spormidt_requires_extra_fields() -> None:
    with _test_client(
        httpx2.MockTransport(lambda _request: httpx2.Response(204))
    ) as client:
        response = _post(
            client,
            _document([_feature(feature_type="spormidt")]),
            profile="fkb_bane",
        )

    assert response.status_code == 422
    errors = " ".join(response.json()["detail"]["errors"])
    assert "hoydereferanse" in errors
    assert "jernbanetype" in errors


def test_rejects_duplicate_identity_before_upstream_calls() -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(204)

    with _test_client(httpx2.MockTransport(handler)) as client:
        response = _post(
            client,
            _document([_feature(), _feature()]),
            profile="fkb_bane",
        )

    assert response.status_code == 422
    assert "duplicate" in " ".join(response.json()["detail"]["errors"])
    assert calls == 0


def test_place_requires_inherited_crs() -> None:
    document = _document([_feature()])
    document.pop("coordRefSys")

    with _test_client(
        httpx2.MockTransport(lambda _request: httpx2.Response(204))
    ) as client:
        response = _post(client, document, profile="fkb_bane")

    assert response.status_code == 422
    assert "place requires coordRefSys" in " ".join(response.json()["detail"]["errors"])


def test_rejects_invalid_json() -> None:
    with _test_client(
        httpx2.MockTransport(lambda _request: httpx2.Response(204))
    ) as client:
        response = client.post(
            "/imports?profile=fkb_bane",
            files={"file": ("bane.json", b"{", "application/json")},
        )

    assert response.status_code == 400


def test_rejects_oversized_upload() -> None:
    with _test_client(
        httpx2.MockTransport(lambda _request: httpx2.Response(204)),
        max_upload_bytes=5,
    ) as client:
        response = client.post(
            "/imports?profile=fkb_bane",
            files={"file": ("bane.json", b"123456", "application/json")},
        )

    assert response.status_code == 413


def test_reports_upstream_failure_as_bad_gateway() -> None:
    transport = httpx2.MockTransport(
        lambda _request: httpx2.Response(503, text="unavailable")
    )

    with _test_client(transport) as client:
        response = _post(client, _document([_feature()]), profile="fkb_bane")

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "message": "FKB-Bane API upsert failed",
        "collection": "jernbaneplattformkant",
        "id": "feature-1",
        "reason": "upstream returned HTTP 503",
    }


def test_rejects_successful_upstream_response_without_uuid() -> None:
    transport = httpx2.MockTransport(
        lambda _request: httpx2.Response(200, json={"id": "not-a-uuid"})
    )

    with _test_client(transport) as client:
        response = _post(client, _document([_feature()]), profile="fkb_bane")

    assert response.status_code == 502
    assert "UUID string id" in response.json()["detail"]["reason"]


def _classic_geojson_document() -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "name": "bane",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::5973"},
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "objid": 31454,
                    "objtype": "Spormidt",
                    "lokalid": "bde1a163-2724-4c48-9101-04c839895292",
                    "identifikasjon_navnerom": (
                        "http://data.geonorge.no/SFKB/FKB-Bane/so"
                    ),
                    "oppdateringsdato": "2026-02-26T09:04:27",
                    "datafangstdato": "2005-04-25T00:00:00",
                    "jernbanetype": "J",
                    "hoydereferanse": "ukjent",
                    "medium": "T",
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [279754.0614235144, 7041951.166005967, 5.86],
                        [279761.8907277025, 7041956.309099379, 5.54],
                    ],
                },
            }
        ],
    }


def _classic_geojson_document_with_alias_names() -> dict[str, Any]:
    document = _classic_geojson_document()
    properties = document["features"][0]["properties"]
    properties["navnerom"] = properties.pop("identifikasjon_navnerom")
    properties["versjonid"] = "2026-02-25 09:10:42.653812000"
    properties["datafangstmetode"] = "fot"
    properties["noyaktighet"] = 19
    return document


def test_imports_classic_geojson_when_filename_ends_with_geojson() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": TRACK_UUID})

    with _test_client(httpx2.MockTransport(handler)) as client:
        response = client.post(
            "/imports?profile=fkb_bane",
            files={
                "file": (
                    "bane.geojson",
                    json.dumps(_classic_geojson_document()),
                    "application/geo+json",
                )
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "total": 1,
        "features": [{"collection": "spormidt", "id": TRACK_UUID}],
    }
    payload = json.loads(requests[0].content)
    assert payload["geometry"]["type"] == "MultiLineString"
    assert payload["geometry"]["coordinates"][0][0][:2] == pytest.approx(
        [279754.0614235144, 7041951.166005967]
    )


def test_classic_geojson_extension_is_case_insensitive() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"id": TRACK_UUID})

    with _test_client(httpx2.MockTransport(handler)) as client:
        response = client.post(
            "/imports?profile=fkb_bane",
            files={
                "file": (
                    "Bane.GEOJSON",
                    json.dumps(_classic_geojson_document()),
                    "application/geo+json",
                )
            },
        )

    assert response.status_code == 200


def test_imports_classic_geojson_with_alias_property_names() -> None:
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"id": TRACK_UUID})

    with _test_client(httpx2.MockTransport(handler)) as client:
        response = client.post(
            "/imports?profile=fkb_bane",
            files={
                "file": (
                    "bane.geojson",
                    json.dumps(_classic_geojson_document_with_alias_names()),
                    "application/geo+json",
                )
            },
        )

    assert response.status_code == 200
    payload = json.loads(requests[0].content)
    assert payload["properties"]["identifikasjon_navnerom"] == (
        "http://data.geonorge.no/SFKB/FKB-Bane/so"
    )


def test_rejects_invalid_classic_geojson_before_upstream_calls() -> None:
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return httpx2.Response(204)

    document = _classic_geojson_document()
    document.pop("crs")

    with _test_client(httpx2.MockTransport(handler)) as client:
        response = client.post(
            "/imports?profile=fkb_bane",
            files={
                "file": (
                    "bane.geojson",
                    json.dumps(document),
                    "application/geo+json",
                )
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "invalid classic GeoJSON document"
    assert "missing CRS" in response.json()["detail"]["errors"][0]
    assert calls == 0


def test_json_uploads_are_not_auto_converted() -> None:
    with _test_client(
        httpx2.MockTransport(lambda _request: httpx2.Response(204))
    ) as client:
        response = client.post(
            "/imports?profile=fkb_bane",
            files={
                "file": (
                    "bane.json",
                    json.dumps(_classic_geojson_document()),
                    "application/json",
                )
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"]["message"] == "invalid JSON-FG document"
