from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from gcimport.app import create_app
from gcimport.config import Settings
from gcimport.importer import prepare_document
from gcimport.profiles import ImportProfile

PLATFORM_UUID = "11111111-1111-4111-8111-111111111111"
TRACK_UUID = "22222222-2222-4222-8222-222222222222"


def _properties(**overrides: Any) -> dict[str, Any]:
    values = {
        "lokalid": "feature-1",
        "identifikasjon_navnerom": "test",
        "oppdateringsdato": "2026-01-01T00:00:00Z",
        "datafangstdato": "2025-01-01T00:00:00Z",
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
            "type": "LineString",
            "coordinates": [[10.7, 59.9], [10.8, 60.0]],
        },
        "properties": properties or _properties(),
    }


def _document(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "coordRefSys": "EPSG:4326",
        "features": features,
    }


def _post(client: TestClient, document: Any) -> httpx.Response:
    return client.post(
        "/imports",
        files={"file": ("bane.json", json.dumps(document), "application/json")},
    )


def _test_client(
    handler: httpx.MockTransport,
    *,
    max_upload_bytes: int = 100_000,
) -> TestClient:
    upstream_client = httpx.AsyncClient(transport=handler)
    app = create_app(
        settings=Settings(
            api_url="https://bane.example/api",
            max_upload_bytes=max_upload_bytes,
        ),
        client=upstream_client,
    )
    return TestClient(app)


def test_imports_place_and_fallback_geometry() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        identifier = (
            TRACK_UUID
            if request.url.path.endswith("/spormidt/items:upsert")
            else PLATFORM_UUID
        )
        return httpx.Response(200, json={"id": identifier})

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

    with _test_client(httpx.MockTransport(handler)) as client:
        response = _post(client, _document([first, second]))

    assert response.status_code == 200
    assert response.json() == {
        "total": 2,
        "features": [
            {"collection": "jernbaneplattformkant", "id": PLATFORM_UUID},
            {"collection": "spormidt", "id": TRACK_UUID},
        ],
    }
    assert [request.url.path for request in requests] == [
        "/api/collections/jernbaneplattformkant/items:upsert",
        "/api/collections/spormidt/items:upsert",
    ]
    for request in requests:
        assert request.headers["content-type"] == "application/geo+json"
        payload = json.loads(request.content)
        assert payload["type"] == "Feature"
        assert payload["geometry"]["type"] == "LineString"
        assert payload["geometry"]["coordinates"][0] != [10.7, 59.9]


def test_retry_returns_the_same_upstream_uuid() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"id": PLATFORM_UUID})

    with _test_client(httpx.MockTransport(handler)) as client:
        first = _post(client, _document([_feature()]))
        retry = _post(client, _document([_feature()]))

    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    assert first.json()["features"][0]["id"] == PLATFORM_UUID
    assert calls == 2


def test_dataset_rules_are_supplied_by_profile() -> None:
    profile = ImportProfile(
        name="roads",
        title="Roads",
        default_api_url="https://example.test/datasets/roads/ogc_api",
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
            "geometry must be a LineString",
        ),
    ],
)
def test_validation_happens_before_upstream_calls(
    mutate: Any,
    expected_error: str,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(204)

    valid = _feature()
    invalid = _feature(properties=_properties(lokalid="feature-2"))
    mutate(invalid)

    with _test_client(httpx.MockTransport(handler)) as client:
        response = _post(client, _document([valid, invalid]))

    assert response.status_code == 422
    assert expected_error in " ".join(response.json()["detail"]["errors"])
    assert calls == 0


def test_spormidt_requires_extra_fields() -> None:
    with _test_client(
        httpx.MockTransport(lambda _request: httpx.Response(204))
    ) as client:
        response = _post(client, _document([_feature(feature_type="spormidt")]))

    assert response.status_code == 422
    errors = " ".join(response.json()["detail"]["errors"])
    assert "hoydereferanse" in errors
    assert "jernbanetype" in errors


def test_rejects_duplicate_identity_before_upstream_calls() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(204)

    with _test_client(httpx.MockTransport(handler)) as client:
        response = _post(client, _document([_feature(), _feature()]))

    assert response.status_code == 422
    assert "duplicate" in " ".join(response.json()["detail"]["errors"])
    assert calls == 0


def test_place_requires_inherited_crs() -> None:
    document = _document([_feature()])
    document.pop("coordRefSys")

    with _test_client(
        httpx.MockTransport(lambda _request: httpx.Response(204))
    ) as client:
        response = _post(client, document)

    assert response.status_code == 422
    assert "place requires coordRefSys" in " ".join(response.json()["detail"]["errors"])


def test_rejects_invalid_json() -> None:
    with _test_client(
        httpx.MockTransport(lambda _request: httpx.Response(204))
    ) as client:
        response = client.post(
            "/imports",
            files={"file": ("bane.json", b"{", "application/json")},
        )

    assert response.status_code == 400


def test_rejects_oversized_upload() -> None:
    with _test_client(
        httpx.MockTransport(lambda _request: httpx.Response(204)),
        max_upload_bytes=5,
    ) as client:
        response = client.post(
            "/imports",
            files={"file": ("bane.json", b"123456", "application/json")},
        )

    assert response.status_code == 413


def test_reports_upstream_failure_as_bad_gateway() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(503, text="unavailable")
    )

    with _test_client(transport) as client:
        response = _post(client, _document([_feature()]))

    assert response.status_code == 502
    assert response.json()["detail"] == {
        "message": "Bane API upsert failed",
        "collection": "jernbaneplattformkant",
        "id": "feature-1",
        "reason": "upstream returned HTTP 503",
    }


def test_rejects_successful_upstream_response_without_uuid() -> None:
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"id": "not-a-uuid"})
    )

    with _test_client(transport) as client:
        response = _post(client, _document([_feature()]))

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


def test_imports_classic_geojson_when_filename_ends_with_geojson() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": TRACK_UUID})

    with _test_client(httpx.MockTransport(handler)) as client:
        response = client.post(
            "/imports",
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
    assert payload["geometry"]["type"] == "LineString"
    assert payload["geometry"]["coordinates"][0][:2] == pytest.approx(
        [279754.0614235144, 7041951.166005967]
    )


def test_classic_geojson_extension_is_case_insensitive() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": TRACK_UUID})

    with _test_client(httpx.MockTransport(handler)) as client:
        response = client.post(
            "/imports",
            files={
                "file": (
                    "Bane.GEOJSON",
                    json.dumps(_classic_geojson_document()),
                    "application/geo+json",
                )
            },
        )

    assert response.status_code == 200


def test_rejects_invalid_classic_geojson_before_upstream_calls() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(204)

    document = _classic_geojson_document()
    document.pop("crs")

    with _test_client(httpx.MockTransport(handler)) as client:
        response = client.post(
            "/imports",
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
        httpx.MockTransport(lambda _request: httpx.Response(204))
    ) as client:
        response = client.post(
            "/imports",
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
