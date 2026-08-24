from __future__ import annotations

import json

import httpx2
import pytest
from fastapi.testclient import TestClient

from gcapi.app import create_app
from gcapi.config import Settings
from gcapi.discovery import DiscoveryError, discover_catalog


def _json_response(
    payload: dict, status_code: int = 200, headers: dict[str, str] | None = None
) -> httpx2.Response:
    return httpx2.Response(
        status_code,
        content=json.dumps(payload).encode("utf-8"),
        headers=headers or {"content-type": "application/json"},
    )


def _build_transport(
    service_desc_base: str = "http://geocomponents.test",
) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:  # noqa: PLR0911, PLR0912
        url = str(request.url)
        method = request.method
        if method == "GET" and url == "http://geocomponents.test/datasets":
            return _json_response(
                {
                    "datasets": [
                        {
                            "id": "cadastre",
                            "title": "Cadastre",
                            "description": "Cadastre data",
                            "links": [
                                {
                                    "rel": "service-desc",
                                    "href": f"{service_desc_base}/datasets/cadastre/ogc_api",
                                }
                            ],
                        },
                        {
                            "id": "bygning",
                            "title": "Bygning",
                            "description": "Bygning data",
                            "links": [
                                {
                                    "rel": "service-desc",
                                    "href": f"{service_desc_base}/datasets/bygning/ogc_api",
                                }
                            ],
                        },
                        {
                            "id": "fkb_bane",
                            "title": "FKB-Bane",
                            "description": "FKB-Bane data",
                            "links": [
                                {
                                    "rel": "service-desc",
                                    "href": f"{service_desc_base}/datasets/fkb_bane/ogc_api",
                                }
                            ],
                        },
                    ]
                }
            )
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/bygning/ogc_api/collections?f=json"
        ):
            return _json_response({"collections": []})
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/bygning/ogc_api/conformance?f=json"
        ):
            return _json_response(
                {
                    "conformsTo": [
                        "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core"
                    ]
                }
            )
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/bygning/ogc_api/processes?f=json"
        ):
            return _json_response({"processes": []})
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/bygning/ogc_api/openapi?f=json"
        ):
            return _json_response({"paths": {}})
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/fkb_bane/ogc_api/collections?f=json"
        ):
            return _json_response({"collections": []})
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/fkb_bane/ogc_api/conformance?f=json"
        ):
            return _json_response(
                {
                    "conformsTo": [
                        "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core"
                    ]
                }
            )
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/fkb_bane/ogc_api/processes?f=json"
        ):
            return _json_response({"processes": []})
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/fkb_bane/ogc_api/openapi?f=json"
        ):
            return _json_response({"paths": {}})
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/cadastre/ogc_api/collections?f=json"
        ):
            return _json_response(
                {
                    "collections": [
                        {
                            "id": "parcels",
                            "title": "Parcels",
                            "links": [
                                {
                                    "rel": "self",
                                    "href": "http://geocomponents.test/datasets/cadastre/ogc_api/collections/parcels",
                                }
                            ],
                        }
                    ]
                }
            )
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/cadastre/ogc_api/conformance?f=json"
        ):
            return _json_response(
                {
                    "conformsTo": [
                        "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
                        "http://www.opengis.net/spec/ogcapi-features-4/1.0/conf/create-replace-delete",
                    ]
                }
            )
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/cadastre/ogc_api/processes?f=json"
        ):
            return _json_response(
                {
                    "processes": [
                        {
                            "id": "hello",
                            "title": "Hello",
                            "version": "1.0.0",
                            "jobControlOptions": ["sync-execute"],
                            "links": [
                                {
                                    "rel": "self",
                                    "href": "http://geocomponents.test/datasets/cadastre/ogc_api/processes/hello",
                                }
                            ],
                        }
                    ]
                }
            )
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/cadastre/ogc_api/openapi?f=json"
        ):
            return _json_response(
                {
                    "paths": {
                        "/collections/parcels/items": {},
                        "/collections/parcels/items/{item_id}": {},
                    }
                }
            )
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/cadastre/ogc_api/collections/parcels?f=json"
        ):
            return _json_response(
                {
                    "id": "parcels",
                    "title": "Parcels",
                    "links": [
                        {
                            "rel": "self",
                            "href": "http://geocomponents.test/datasets/cadastre/ogc_api/collections/parcels",
                        },
                        {
                            "rel": "items",
                            "href": "http://geocomponents.test/datasets/cadastre/ogc_api/collections/parcels/items",
                        },
                    ],
                }
            )
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/cadastre/ogc_api/collections/parcels/schema"
        ):
            return _json_response(
                {"type": "object", "properties": {"id": {"type": "string"}}}
            )
        if (
            method == "OPTIONS"
            and url
            == "http://geocomponents.test/datasets/cadastre/ogc_api/collections/parcels/items"
        ):
            return httpx2.Response(200, headers={"Allow": "GET, HEAD, OPTIONS, POST"})
        if (
            method == "OPTIONS"
            and url
            == "http://geocomponents.test/datasets/cadastre/ogc_api/collections/parcels/items/__gcapi_probe__"
        ):
            return httpx2.Response(
                200, headers={"Allow": "GET, HEAD, OPTIONS, PUT, PATCH, DELETE"}
            )
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/cadastre/ogc_api/processes/hello?f=json"
        ):
            return _json_response(
                {
                    "id": "hello",
                    "title": "Hello",
                    "version": "1.0.0",
                    "jobControlOptions": ["sync-execute"],
                    "links": [
                        {
                            "rel": "self",
                            "href": "http://geocomponents.test/datasets/cadastre/ogc_api/processes/hello",
                        },
                        {
                            "rel": "http://www.opengis.net/def/rel/ogc/1.0/execute",
                            "href": "http://geocomponents.test/datasets/cadastre/ogc_api/processes/hello/execution",
                        },
                    ],
                }
            )
        if (
            method == "GET"
            and url
            == "http://geocomponents.test/datasets/cadastre/ogc_api/collections/parcels/items?f=json&limit=1"
        ):
            return _json_response(
                {
                    "type": "FeatureCollection",
                    "links": [
                        {
                            "rel": "self",
                            "href": "http://geocomponents.test/datasets/cadastre/ogc_api/collections/parcels/items?f=json&limit=1",
                        }
                    ],
                    "features": [],
                }
            )
        if (
            method == "POST"
            and url
            == "http://geocomponents.test/datasets/cadastre/ogc_api/collections/parcels/items"
        ):
            return _json_response(
                {"id": "feature-1"},
                status_code=201,
                headers={
                    "content-type": "application/geo+json",
                    "Location": "http://geocomponents.test/datasets/cadastre/ogc_api/collections/parcels/items/feature-1",
                },
            )
        if (
            method == "POST"
            and url
            == "http://geocomponents.test/datasets/cadastre/ogc_api/processes/hello/execution"
        ):
            return httpx2.Response(
                200,
                text="Dataset echoes: world",
                headers={"content-type": "text/plain; charset=utf-8"},
            )
        if (
            method == "POST"
            and url == "http://gcjobs.test/processes/import-fkb-bane/execution"
        ):
            return _json_response(
                {
                    "type": "process",
                    "jobID": "job-1",
                    "processID": "import-fkb-bane",
                    "status": "accepted",
                    "message": "Import accepted",
                    "links": [
                        {
                            "href": "http://gcjobs.test/jobs/job-1",
                            "rel": "self",
                            "type": "application/json",
                            "title": "This document",
                        },
                        {
                            "href": "http://gcjobs.test/jobs",
                            "rel": "up",
                            "type": "application/json",
                            "title": "Job list",
                        },
                    ],
                },
                status_code=201,
                headers={"Location": "http://gcjobs.test/jobs/job-1"},
            )
        if method == "GET" and url == "http://gcjobs.test/jobs?limit=10000":
            return _json_response(
                {
                    "jobs": [
                        {
                            "type": "process",
                            "jobID": "job-1",
                            "status": "accepted",
                            "phase": "accepted",
                            "processID": "import-fkb-bane",
                            "links": [
                                {
                                    "href": "http://gcjobs.test/jobs/job-1",
                                    "rel": "self",
                                    "type": "application/json",
                                    "title": "This document",
                                },
                                {
                                    "href": "http://gcjobs.test/jobs",
                                    "rel": "up",
                                    "type": "application/json",
                                    "title": "Job list",
                                },
                            ],
                            "updated": "2026-08-24T09:00:00Z",
                            "totalFeatures": None,
                            "processedFeatures": 0,
                            "succeededFeatures": 0,
                            "failedFeatures": 0,
                            "processedBatches": 0,
                            "succeededBatches": 0,
                            "failedBatches": 0,
                            "created": "2026-08-24T09:00:00Z",
                            "message": "Import accepted",
                        },
                        {
                            "type": "process",
                            "jobID": "job-2",
                            "status": "successful",
                            "phase": "completed",
                            "processID": "import-bygning",
                            "links": [
                                {
                                    "href": "http://gcjobs.test/jobs/job-2",
                                    "rel": "self",
                                    "type": "application/json",
                                    "title": "This document",
                                },
                                {
                                    "href": "http://gcjobs.test/jobs",
                                    "rel": "up",
                                    "type": "application/json",
                                    "title": "Job list",
                                },
                                {
                                    "href": "http://gcjobs.test/jobs/job-2/results",
                                    "rel": "http://www.opengis.net/def/rel/ogc/1.0/results",
                                    "type": "application/json",
                                    "title": "Job results",
                                },
                            ],
                            "updated": "2026-08-24T09:22:00Z",
                            "totalFeatures": 8,
                            "processedFeatures": 8,
                            "succeededFeatures": 8,
                            "failedFeatures": 0,
                            "processedBatches": 2,
                            "succeededBatches": 2,
                            "failedBatches": 0,
                            "created": "2026-08-24T09:15:00Z",
                            "started": "2026-08-24T09:15:00Z",
                            "finished": "2026-08-24T09:22:00Z",
                            "message": "Import completed",
                            "progress": 100,
                        },
                    ]
                }
            )
        if method == "GET" and url == "http://gcjobs.test/jobs/job-1":
            return _json_response(
                {
                    "type": "process",
                    "jobID": "job-1",
                    "status": "successful",
                    "phase": "completed",
                    "processID": "import-fkb-bane",
                    "links": [
                        {
                            "href": "http://gcjobs.test/jobs/job-1",
                            "rel": "self",
                            "type": "application/json",
                            "title": "This document",
                        },
                        {
                            "href": "http://gcjobs.test/jobs",
                            "rel": "up",
                            "type": "application/json",
                            "title": "Job list",
                        },
                        {
                            "href": "http://gcjobs.test/jobs/job-1/results",
                            "rel": "http://www.opengis.net/def/rel/ogc/1.0/results",
                            "type": "application/json",
                            "title": "Job results",
                        },
                    ],
                    "updated": "2026-08-24T09:05:00Z",
                    "totalFeatures": 4,
                    "processedFeatures": 4,
                    "succeededFeatures": 4,
                    "failedFeatures": 0,
                    "processedBatches": 2,
                    "succeededBatches": 2,
                    "failedBatches": 0,
                    "created": "2026-08-24T09:00:00Z",
                    "started": "2026-08-24T09:00:00Z",
                    "finished": "2026-08-24T09:05:00Z",
                    "message": "Import completed",
                    "progress": 100,
                }
            )
        if method == "GET" and url == "http://gcjobs.test/jobs/job-1/results":
            return _json_response(
                {
                    "summary": {
                        "jobID": "job-1",
                        "processedFeatures": 4,
                        "succeededFeatures": 4,
                        "failedFeatures": 0,
                        "processedBatches": 2,
                        "succeededBatches": 2,
                        "failedBatches": 0,
                        "totalFeatures": 4,
                        "completed": "2026-08-24T09:05:00Z",
                    }
                }
            )
        raise AssertionError(f"Unhandled request: {method} {url}")

    return httpx2.MockTransport(handler)


@pytest.mark.anyio
async def test_discover_catalog_builds_namespaced_routes() -> None:
    settings = Settings(
        public_url="http://gcapi.test",
        geocomponents_url="http://geocomponents.test",
        gcjobs_url="http://gcjobs.test",
    )
    async with httpx2.AsyncClient(
        transport=_build_transport(), trust_env=False
    ) as client:
        catalog = await discover_catalog(client, settings)

    assert sorted(catalog.collections) == ["cadastre.parcels"]
    assert sorted(catalog.processes) == ["cadastre.hello"]
    assert any("ogcapi-features-4" in uri for uri in catalog.feature_conformance)


@pytest.mark.anyio
async def test_discover_catalog_rebases_advertised_dataset_urls_to_configured_upstream() -> (
    None
):
    settings = Settings(
        public_url="http://gcapi.test",
        geocomponents_url="http://geocomponents.test",
        gcjobs_url="http://gcjobs.test",
    )
    async with httpx2.AsyncClient(
        transport=_build_transport(service_desc_base="http://localhost:8000"),
        trust_env=False,
    ) as client:
        catalog = await discover_catalog(client, settings)

    assert catalog.datasets["cadastre"].upstream_base_url == (
        "http://geocomponents.test/datasets/cadastre/ogc_api"
    )


@pytest.mark.anyio
async def test_discover_catalog_rejects_duplicate_canonical_collection_ids() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if str(request.url) == "http://geocomponents.test/datasets":
            return _json_response(
                {
                    "datasets": [
                        {
                            "id": "a",
                            "links": [
                                {
                                    "rel": "service-desc",
                                    "href": "http://geocomponents.test/datasets/a/ogc_api",
                                }
                            ],
                        },
                        {
                            "id": "a",
                            "links": [
                                {
                                    "rel": "service-desc",
                                    "href": "http://geocomponents.test/datasets/a2/ogc_api",
                                }
                            ],
                        },
                    ]
                }
            )
        raise AssertionError(f"Unhandled request: {request.method} {request.url}")

    settings = Settings(
        public_url="http://gcapi.test",
        geocomponents_url="http://geocomponents.test",
        gcjobs_url="http://gcjobs.test",
    )
    async with httpx2.AsyncClient(
        transport=httpx2.MockTransport(handler),
        trust_env=False,
    ) as client:
        with pytest.raises(DiscoveryError, match="Duplicate dataset id 'a'"):
            await discover_catalog(client, settings)


def test_gcapi_proxies_and_rewrites_collection_and_job_routes() -> None:
    settings = Settings(
        public_url="http://gcapi.test",
        geocomponents_url="http://geocomponents.test",
        gcjobs_url="http://gcjobs.test",
    )
    app = create_app(
        settings=settings,
        client=httpx2.AsyncClient(transport=_build_transport(), trust_env=False),
    )

    with TestClient(app) as client:
        datasets = client.get("/datasets")
        assert datasets.status_code == 200
        cadastre_dataset = next(
            dataset
            for dataset in datasets.json()["datasets"]
            if dataset["id"] == "cadastre"
        )
        assert cadastre_dataset["links"][0]["href"] == (
            "http://gcapi.test/datasets/cadastre/ogc_api/"
        )

        landing = client.get("/datasets/cadastre/ogc_api/")
        assert landing.status_code == 200
        assert landing.json()["links"][3]["href"] == (
            "http://gcapi.test/datasets/cadastre/ogc_api/collections"
        )

        collections = client.get("/datasets/cadastre/ogc_api/collections")
        assert collections.status_code == 200
        assert collections.json()["collections"][0]["id"] == "parcels"

        items = client.get(
            "/datasets/cadastre/ogc_api/collections/parcels/items",
            params={"f": "json", "limit": 1},
        )
        assert items.status_code == 200
        assert (
            items.json()["links"][0]["href"]
            == "http://gcapi.test/datasets/cadastre/ogc_api/collections/parcels/items?f=json&limit=1"
        )

        created = client.post(
            "/datasets/cadastre/ogc_api/collections/parcels/items",
            content=json.dumps({"type": "Feature", "properties": {}, "geometry": None}),
            headers={"content-type": "application/geo+json"},
        )
        assert created.status_code == 201
        assert (
            created.headers["location"]
            == "http://gcapi.test/datasets/cadastre/ogc_api/collections/parcels/items/feature-1"
        )

        process = client.get("/datasets/cadastre/ogc_api/processes/hello")
        assert process.status_code == 200
        assert process.json()["id"] == "hello"
        assert (
            process.json()["links"][-1]["href"]
            == "http://gcapi.test/datasets/cadastre/ogc_api/jobs?processID=hello&type=process"
        )

        executed = client.post(
            "/datasets/cadastre/ogc_api/processes/hello/execution",
            content=json.dumps({"inputs": {"name": "world"}}),
            headers={"content-type": "application/json"},
        )
        assert executed.status_code == 200
        assert "Dataset echoes: world" in executed.text

        accepted = client.post(
            "/datasets/fkb_bane/ogc_api/processes/import-fkb-bane/execution",
            files={"file": ("data.geojson", b"{}", "application/geo+json")},
        )
        assert accepted.status_code == 201
        assert (
            accepted.headers["location"]
            == "http://gcapi.test/datasets/fkb_bane/ogc_api/jobs/job-1"
        )
        assert accepted.json()["status"] == "accepted"

        jobs = client.get("/datasets/fkb_bane/ogc_api/jobs")
        assert jobs.status_code == 200
        assert jobs.json()["jobs"][0]["processID"] == "import-fkb-bane"

        filtered_jobs = client.get(
            "/datasets/bygning/ogc_api/jobs",
            params={
                "type": "process",
                "processID": "import-bygning",
                "status": "successful",
                "datetime": "2026-08-24T09:10:00Z/2026-08-24T09:30:00Z",
                "minDuration": 300,
                "maxDuration": 900,
            },
        )
        assert filtered_jobs.status_code == 200
        assert filtered_jobs.json()["jobs"] == [
            {
                "type": "process",
                "jobID": "job-2",
                "status": "successful",
                "links": [
                    {
                        "href": "http://gcapi.test/datasets/bygning/ogc_api/jobs/job-2",
                        "rel": "self",
                        "type": "application/json",
                        "title": "This document",
                    },
                    {
                        "href": "http://gcapi.test/datasets/bygning/ogc_api/jobs",
                        "rel": "up",
                        "type": "application/json",
                        "title": "Job list",
                    },
                    {
                        "href": "http://gcapi.test/datasets/bygning/ogc_api/jobs/job-2/results",
                        "rel": "http://www.opengis.net/def/rel/ogc/1.0/results",
                        "type": "application/json",
                        "title": "Job results",
                    },
                ],
                "updated": "2026-08-24T09:22:00Z",
                "phase": "completed",
                "totalFeatures": 8,
                "processedFeatures": 8,
                "succeededFeatures": 8,
                "failedFeatures": 0,
                "processedBatches": 2,
                "succeededBatches": 2,
                "failedBatches": 0,
                "processID": "import-bygning",
                "created": "2026-08-24T09:15:00Z",
                "started": "2026-08-24T09:15:00Z",
                "finished": "2026-08-24T09:22:00Z",
                "message": "Import completed",
                "progress": 100,
            }
        ]
        assert filtered_jobs.json()["links"][0]["href"] == (
            "http://testserver/datasets/bygning/ogc_api/jobs?type=process&processID=import-bygning&status=successful&datetime=2026-08-24T09%3A10%3A00Z%2F2026-08-24T09%3A30%3A00Z&minDuration=300&maxDuration=900"
        )

        job = client.get("/datasets/fkb_bane/ogc_api/jobs/job-1")
        assert job.status_code == 200
        assert job.json()["status"] == "successful"

        results = client.get("/datasets/fkb_bane/ogc_api/jobs/job-1/results")
        assert results.status_code == 200
        assert results.json()["summary"]["succeededFeatures"] == 4
