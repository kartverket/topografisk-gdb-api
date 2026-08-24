from __future__ import annotations

import httpx2
from fastapi.testclient import TestClient

from gcapi.app import create_app
from gcapi.catalog import CatalogSnapshot
from gcapi.config import Settings


def test_create_app_uses_injected_client() -> None:
    settings = Settings(
        public_url="http://localhost:8004",
        geocomponents_url="http://localhost:8000",
        gcjobs_url="http://localhost:8003",
    )
    client = httpx2.AsyncClient(trust_env=False)
    app = create_app(settings=settings, client=client, catalog=CatalogSnapshot())

    with TestClient(app) as test_client:
        response = test_client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "gcapi"}
        assert app.state.settings == settings
        assert app.state.http_client is client


def test_root_reports_configured_upstreams() -> None:
    settings = Settings(
        public_url="http://localhost:8004",
        geocomponents_url="http://localhost:8000",
        gcjobs_url="http://localhost:8003",
    )
    app = create_app(
        settings=settings,
        client=httpx2.AsyncClient(trust_env=False),
        catalog=CatalogSnapshot(),
    )

    with TestClient(app) as test_client:
        response = test_client.get("/")

    assert response.status_code == 200
    assert response.json()["links"][0]["href"] == "http://localhost:8004/"


def test_conformance_only_reports_supported_public_classes() -> None:
    settings = Settings(
        public_url="http://localhost:8004",
        geocomponents_url="http://localhost:8000",
        gcjobs_url="http://localhost:8003",
    )
    catalog = CatalogSnapshot(
        feature_conformance=(
            "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
            "http://www.opengis.net/spec/ogcapi-features-4/1.0/conf/create-replace-delete",
        )
    )
    app = create_app(
        settings=settings,
        client=httpx2.AsyncClient(trust_env=False),
        catalog=catalog,
    )

    with TestClient(app) as test_client:
        response = test_client.get("/conformance")

    assert response.status_code == 200
    assert response.json()["conformsTo"] == [
        "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core"
    ]


def test_create_app_always_allows_wildcard_cors() -> None:
    app = create_app(
        settings=Settings(
            public_url="http://localhost:8004",
            geocomponents_url="http://localhost:8000",
            gcjobs_url="http://localhost:8003",
        ),
        client=httpx2.AsyncClient(trust_env=False),
        catalog=CatalogSnapshot(),
    )

    with TestClient(app) as test_client:
        response = test_client.options(
            "/collections",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
