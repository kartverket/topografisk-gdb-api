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


def _build_transport() -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        url = str(request.url)
        method = request.method
        if method == "GET" and url == "http://geocomponents.test/collections":
            return _json_response(
                {
                    "collections": [
                        {
                            "id": "parcels",
                            "links": [
                                {
                                    "rel": "self",
                                    "href": "http://geocomponents.test/collections/parcels",
                                }
                            ],
                        }
                    ]
                }
            )
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/collections/parcels/items?f=json&limit=1"
        ):
            return _json_response(
                {
                    "type": "FeatureCollection",
                    "links": [
                        {
                            "rel": "self",
                            "href": "http://geocomponents.test/collections/parcels/items?f=json&limit=1",
                        }
                    ],
                    "features": [],
                }
            )
        if (
            method == "POST"
            and url == "http://geocomponents.test/collections/parcels/items"
        ):
            return _json_response(
                {"id": "feature-1"},
                status_code=201,
                headers={
                    "content-type": "application/geo+json",
                    "Location": "http://geocomponents.test/collections/parcels/items/feature-1",
                },
            )
        if method == "GET" and url == "http://geocomponents.test/processes":
            return _json_response(
                {
                    "processes": [
                        {
                            "id": "import",
                            "links": [
                                {
                                    "href": "http://geocomponents.test/processes/import",
                                    "rel": "self",
                                    "type": "application/json",
                                    "title": "This document",
                                },
                            ],
                        }
                    ]
                }
            )
        if method == "GET" and url == "http://geocomponents.test/processes/import":
            return _json_response(
                {
                    "id": "import",
                    "links": [
                        {
                            "href": "http://geocomponents.test/processes/import",
                            "rel": "self",
                            "type": "application/json",
                            "title": "This document",
                        },
                        {
                            "href": "http://geocomponents.test/processes/import/execution",
                            "rel": "http://www.opengis.net/def/rel/ogc/1.0/execute",
                            "type": "application/json",
                            "title": "Execute",
                        },
                    ],
                }
            )
        if (
            method == "POST"
            and url == "http://geocomponents.test/processes/import/execution"
        ):
            return _json_response(
                {"jobID": "job-2", "status": "accepted"},
                status_code=201,
                headers={"Location": "http://geocomponents.test/jobs/job-2"},
            )
        raise AssertionError(f"Unhandled request: {method} {url}")

    return httpx2.MockTransport(handler)


def test_gcapi_is_a_generic_passthrough_proxy() -> None:
    app = create_app(
        settings=Settings(geocomponents_url="http://geocomponents.test"),
        client=httpx2.AsyncClient(transport=_build_transport(), trust_env=False),
    )

    with TestClient(app) as client:
        collections = client.get("/collections")
        assert collections.status_code == 200
        assert collections.json()["collections"][0]["id"] == "parcels"
        assert collections.json()["collections"][0]["links"][0]["href"] == (
            "http://geocomponents.test/collections/parcels"
        )

        items = client.get(
            "/collections/parcels/items",
            params={"f": "json", "limit": 1},
        )
        assert items.status_code == 200
        assert (
            items.json()["links"][0]["href"]
            == "http://geocomponents.test/collections/parcels/items?f=json&limit=1"
        )

        created = client.post(
            "/collections/parcels/items",
            content=json.dumps({"type": "Feature", "properties": {}, "geometry": None}),
            headers={"content-type": "application/geo+json"},
        )
        assert created.status_code == 201
        assert (
            created.headers["location"]
            == "http://geocomponents.test/collections/parcels/items/feature-1"
        )

        processes = client.get("/processes")
        assert processes.status_code == 200
        assert processes.json()["processes"][0]["links"][0]["href"] == (
            "http://geocomponents.test/processes/import"
        )

        process = client.get("/processes/import")
        assert process.status_code == 200
        assert process.json()["links"][1]["href"] == (
            "http://geocomponents.test/processes/import/execution"
        )

        executed = client.post(
            "/processes/import/execution",
            files={"file": ("data.geojson", b"{}", "application/geo+json")},
        )
        assert executed.status_code == 201
        assert executed.headers["location"] == ("http://geocomponents.test/jobs/job-2")
