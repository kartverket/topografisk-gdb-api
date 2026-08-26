from __future__ import annotations

import json

import httpx2
from fastapi.testclient import TestClient

from gcapi.app import create_app
from gcapi.config import Settings


def _json_response(
    payload: dict, status_code: int = 200, headers: dict[str, str] | None = None
) -> httpx2.Response:
    return httpx2.Response(
        status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers=headers or {"content-type": "application/json"},
    )


def test_create_app_uses_injected_client() -> None:
    settings = Settings(
        geocomponents_url="http://localhost:8000",
    )
    client = httpx2.AsyncClient(trust_env=False)
    app = create_app(settings=settings, client=client)

    with TestClient(app) as test_client:
        response = test_client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "gcapi"}
        assert app.state.settings == settings
        assert app.state.http_client is client


def test_root_redirects_to_datasets() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET"
        assert str(request.url) == "http://localhost:8000"
        return _json_response({"service": "geocomponents"})

    app = create_app(
        settings=Settings(geocomponents_url="http://localhost:8000"),
        client=httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler), trust_env=False
        ),
    )

    with TestClient(app) as test_client:
        response = test_client.get("/")

    assert response.status_code == 200
    assert response.json() == {"service": "geocomponents"}


def test_proxy_forwards_nested_paths_query_and_json_without_rewriting() -> None:
    seen_requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen_requests.append(request)
        assert request.method == "GET"
        assert (
            str(request.url)
            == "http://localhost:8000/datasets/cadastre/ogc_api/collections?f=json&limit=1"
        )
        return _json_response(
            {
                "links": [
                    {
                        "rel": "self",
                        "href": "http://localhost:8000/datasets/cadastre/ogc_api/collections?f=json&limit=1",
                    }
                ]
            }
        )

    app = create_app(
        settings=Settings(geocomponents_url="http://localhost:8000"),
        client=httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler), trust_env=False
        ),
    )

    with TestClient(app) as test_client:
        response = test_client.get(
            "/datasets/cadastre/ogc_api/collections",
            params={"f": "json", "limit": 1},
        )

    assert response.status_code == 200
    assert response.json()["links"][0]["href"] == (
        "http://localhost:8000/datasets/cadastre/ogc_api/collections?f=json&limit=1"
    )
    assert seen_requests[0].headers["host"] == "localhost:8000"


def test_dataset_import_process_paths_proxy_to_gcjobs_when_configured() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "POST"
        assert (
            str(request.url)
            == "http://gcjobs.test/datasets/cadastre/ogc_api/processes/import/execution"
        )
        return _json_response(
            {"jobID": "job-2", "status": "accepted"},
            status_code=201,
            headers={
                "content-type": "application/json",
                "Location": "http://gcjobs.test/datasets/cadastre/ogc_api/jobs/job-2",
            },
        )

    app = create_app(
        settings=Settings(
            geocomponents_url="http://geocomponents.test",
            gcjobs_url="http://gcjobs.test",
        ),
        client=httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler), trust_env=False
        ),
    )

    with TestClient(app) as test_client:
        response = test_client.post(
            "/datasets/cadastre/ogc_api/processes/import/execution",
            files={"file": ("data.geojson", b"{}", "application/geo+json")},
        )

    assert response.status_code == 201
    assert response.headers["location"] == (
        "http://gcjobs.test/datasets/cadastre/ogc_api/jobs/job-2"
    )
    assert response.json() == {"jobID": "job-2", "status": "accepted"}


def test_dataset_job_paths_proxy_to_gcjobs_when_configured() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET"
        assert (
            str(request.url)
            == "http://gcjobs.test/datasets/cadastre/ogc_api/jobs/job-2/results?f=json"
        )
        return _json_response(
            {
                "jobID": "job-2",
                "status": "successful",
                "links": [
                    {
                        "rel": "self",
                        "href": "http://gcjobs.test/datasets/cadastre/ogc_api/jobs/job-2/results?f=json",
                    }
                ],
            }
        )

    app = create_app(
        settings=Settings(
            geocomponents_url="http://geocomponents.test",
            gcjobs_url="http://gcjobs.test",
        ),
        client=httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler), trust_env=False
        ),
    )

    with TestClient(app) as test_client:
        response = test_client.get(
            "/datasets/cadastre/ogc_api/jobs/job-2/results",
            params={"f": "json"},
        )

    assert response.status_code == 200
    assert response.json()["links"][0]["href"] == (
        "http://gcjobs.test/datasets/cadastre/ogc_api/jobs/job-2/results?f=json"
    )


def test_proxy_passes_request_body_and_location_headers_through() -> None:
    body_chunks: list[bytes] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "POST"
        assert str(request.url) == "http://localhost:8000/imports"
        body_chunks.append(request.read())
        return httpx2.Response(
            201,
            content=b'{"id":"feature-1"}',
            headers={
                "content-type": "application/json",
                "Location": "http://localhost:8000/imports/feature-1",
            },
        )

    app = create_app(
        settings=Settings(geocomponents_url="http://localhost:8000"),
        client=httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler), trust_env=False
        ),
    )

    with TestClient(app) as test_client:
        response = test_client.post(
            "/imports",
            content=b'{"name":"world"}',
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 201
    assert response.headers["location"] == "http://localhost:8000/imports/feature-1"
    assert response.json() == {"id": "feature-1"}
    assert body_chunks == [b'{"name":"world"}']


def test_create_app_always_allows_wildcard_cors() -> None:
    app = create_app(
        settings=Settings(
            geocomponents_url="http://localhost:8000",
        ),
        client=httpx2.AsyncClient(trust_env=False),
    )

    with TestClient(app) as test_client:
        response = test_client.options(
            "/datasets/cadastre/ogc_api/collections",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
