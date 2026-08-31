from __future__ import annotations

import json

import httpx2
from fastapi.testclient import TestClient

from gcapi.app import AUTH_CACHE_TTL_SECONDS, create_app
from gcapi.config import Settings


def _json_response(
    payload: dict, status_code: int = 200, headers: dict[str, str] | None = None
) -> httpx2.Response:
    return httpx2.Response(
        status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers=headers or {"content-type": "application/json"},
    )


def _authorize_or_forward(
    request: httpx2.Request,
    *,
    authorize_url: str,
    next_handler,
) -> httpx2.Response:
    if str(request.url) == authorize_url:
        assert request.method == "POST"
        assert json.loads(request.read().decode("utf-8")) == {"client_id": None}
        return _json_response({"authorized": True, "client_id": None})
    return next_handler(request)


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
        assert app.state.authorization_cache.ttl == AUTH_CACHE_TTL_SECONDS


def test_root_redirects_to_datasets() -> None:
    def downstream(request: httpx2.Request) -> httpx2.Response:
        assert request.method == "GET"
        assert str(request.url) == "http://localhost:8000"
        return _json_response({"service": "geocomponents"})

    def handler(request: httpx2.Request) -> httpx2.Response:
        return _authorize_or_forward(
            request,
            authorize_url="http://localhost:8002/authorize",
            next_handler=downstream,
        )

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

    def downstream(request: httpx2.Request) -> httpx2.Response:
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

    def handler(request: httpx2.Request) -> httpx2.Response:
        return _authorize_or_forward(
            request,
            authorize_url="http://localhost:8002/authorize",
            next_handler=downstream,
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
    def downstream(request: httpx2.Request) -> httpx2.Response:
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

    def handler(request: httpx2.Request) -> httpx2.Response:
        return _authorize_or_forward(
            request,
            authorize_url="http://localhost:8002/authorize",
            next_handler=downstream,
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
    def downstream(request: httpx2.Request) -> httpx2.Response:
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

    def handler(request: httpx2.Request) -> httpx2.Response:
        return _authorize_or_forward(
            request,
            authorize_url="http://localhost:8002/authorize",
            next_handler=downstream,
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

    def downstream(request: httpx2.Request) -> httpx2.Response:
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

    def handler(request: httpx2.Request) -> httpx2.Response:
        return _authorize_or_forward(
            request,
            authorize_url="http://localhost:8002/authorize",
            next_handler=downstream,
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


def test_proxy_passes_authorization_header_through_without_setting_cookie() -> None:
    seen_urls: list[str] = []

    def downstream(request: httpx2.Request) -> httpx2.Response:
        seen_urls.append(str(request.url))
        assert str(request.url) == "http://geocomponents.test/datasets"
        assert request.headers["authorization"] == "Bearer api-token"
        return _json_response({"collections": []})

    def handler(request: httpx2.Request) -> httpx2.Response:
        return _authorize_or_forward(
            request,
            authorize_url="http://localhost:8002/authorize",
            next_handler=downstream,
        )

    app = create_app(
        settings=Settings(
            geocomponents_url="http://geocomponents.test",
        ),
        client=httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler), trust_env=False
        ),
    )

    with TestClient(app) as test_client:
        response = test_client.get(
            "/datasets",
            headers={"authorization": "Bearer api-token"},
        )

    assert response.status_code == 200
    assert response.json() == {"collections": []}
    assert "set-cookie" not in response.headers
    assert seen_urls == ["http://geocomponents.test/datasets"]


def test_authorization_calls_configured_gccore_url() -> None:
    seen_urls: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen_urls.append(str(request.url))
        return _authorize_or_forward(
            request,
            authorize_url="http://gccore.test/authorize",
            next_handler=lambda forwarded: _json_response({"collections": []}),
        )

    app = create_app(
        settings=Settings(
            geocomponents_url="http://geocomponents.test",
            gccore_url="http://gccore.test",
        ),
        client=httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler), trust_env=False
        ),
    )

    with TestClient(app) as test_client:
        response = test_client.get("/datasets")

    assert response.status_code == 200
    assert seen_urls[0] == "http://gccore.test/authorize"


def test_authorization_uses_ttl_cache_for_same_client_id() -> None:
    authorize_calls = 0
    downstream_calls = 0

    def downstream(request: httpx2.Request) -> httpx2.Response:
        nonlocal downstream_calls
        downstream_calls += 1
        return _json_response({"collections": []})

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal authorize_calls
        if str(request.url) == "http://gccore.test/authorize":
            authorize_calls += 1
        return _authorize_or_forward(
            request,
            authorize_url="http://gccore.test/authorize",
            next_handler=downstream,
        )

    app = create_app(
        settings=Settings(
            geocomponents_url="http://geocomponents.test",
            gccore_url="http://gccore.test",
        ),
        client=httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler), trust_env=False
        ),
    )

    with TestClient(app) as test_client:
        first_response = test_client.get("/datasets")
        second_response = test_client.get("/datasets")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert authorize_calls == 1
    assert downstream_calls == 2


def test_authorization_failure_returns_problem_response() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if str(request.url) == "http://gccore.test/authorize":
            assert request.method == "POST"
            return _json_response({"authorized": False, "client_id": None})
        raise AssertionError(
            "proxy target should not be called when authorization fails"
        )

    app = create_app(
        settings=Settings(
            geocomponents_url="http://geocomponents.test",
            gccore_url="http://gccore.test",
        ),
        client=httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler), trust_env=False
        ),
    )

    with TestClient(app) as test_client:
        response = test_client.get("/datasets")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Unauthorized"
