from __future__ import annotations

from gcapi.catalog import CatalogSnapshot
from gcapi.config import Settings
from gcapi.rewrite import dataset_api_path, public_url

IMPORT_PROCESS_ID = "import"
IMPORT_DATASETS = frozenset({"bygning", "fkb_bane"})


def build_openapi(
    settings: Settings, catalog: CatalogSnapshot, dataset_id: str
) -> dict:
    collection_ids = sorted(
        route.local_id
        for route in catalog.collections.values()
        if route.dataset_id == dataset_id
    )
    process_ids = sorted(
        {
            route.local_id
            for route in catalog.processes.values()
            if route.dataset_id == dataset_id
        }
        | ({IMPORT_PROCESS_ID} if dataset_id in IMPORT_DATASETS else set())
    )
    server_url = public_url(settings, dataset_api_path(dataset_id))
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "gcapi",
            "version": "0.1.0",
            "description": "Canonical OGC facade for geocomponents and gcjobs.",
        },
        "servers": [{"url": server_url}],
        "paths": {
            "/": {"get": {"responses": {"200": {"description": "Landing page"}}}},
            "/conformance": {
                "get": {"responses": {"200": {"description": "Conformance"}}}
            },
            "/openapi": {
                "get": {"responses": {"200": {"description": "OpenAPI document"}}}
            },
            "/collections": {
                "get": {"responses": {"200": {"description": "Collections"}}}
            },
            "/collections/{collectionId}": {
                "get": {
                    "parameters": [
                        {
                            "name": "collectionId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "enum": collection_ids},
                        }
                    ],
                    "responses": {
                        "200": {"description": "Collection"},
                        "404": {"description": "Not found"},
                    },
                }
            },
            "/collections/{collectionId}/schema": {
                "get": {
                    "parameters": [
                        {
                            "name": "collectionId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "enum": collection_ids},
                        }
                    ],
                    "responses": {"200": {"description": "Collection schema"}},
                }
            },
            "/collections/{collectionId}/items": {
                "get": {"responses": {"200": {"description": "Features"}}},
                "post": {
                    "responses": {
                        "201": {"description": "Created"},
                        "405": {"description": "Method not allowed"},
                    }
                },
            },
            "/collections/{collectionId}/items/{featureId}": {
                "get": {"responses": {"200": {"description": "Feature"}}},
                "put": {
                    "responses": {
                        "200": {"description": "Updated"},
                        "204": {"description": "Updated"},
                    }
                },
                "patch": {"responses": {"204": {"description": "Patched"}}},
                "delete": {
                    "responses": {
                        "200": {"description": "Deleted"},
                        "204": {"description": "Deleted"},
                    }
                },
            },
            "/collections/{collectionId}/items:upsert": {
                "post": {
                    "responses": {
                        "200": {"description": "Upserted"},
                        "405": {"description": "Method not allowed"},
                    }
                }
            },
            "/processes": {"get": {"responses": {"200": {"description": "Processes"}}}},
            "/processes/{processId}": {
                "get": {
                    "parameters": [
                        {
                            "name": "processId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "enum": process_ids},
                        }
                    ],
                    "responses": {
                        "200": {"description": "Process description"},
                        "404": {"description": "Not found"},
                    },
                }
            },
            "/processes/{processId}/execution": {
                "post": {
                    "parameters": [
                        {
                            "name": "processId",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "enum": process_ids},
                        }
                    ],
                    "responses": {
                        "200": {"description": "Synchronous result"},
                        "201": {
                            "description": "Asynchronous job created",
                            "headers": {
                                "Location": {
                                    "schema": {"type": "string", "format": "uri"}
                                }
                            },
                        },
                    },
                }
            },
            "/jobs": {
                "get": {
                    "parameters": [
                        {
                            "name": "type",
                            "in": "query",
                            "required": False,
                            "style": "form",
                            "explode": False,
                            "schema": {"type": "array", "items": {"type": "string"}},
                        },
                        {
                            "name": "processID",
                            "in": "query",
                            "required": False,
                            "style": "form",
                            "explode": False,
                            "schema": {
                                "type": "array",
                                "items": {"type": "string", "enum": process_ids},
                            },
                        },
                        {
                            "name": "status",
                            "in": "query",
                            "required": False,
                            "style": "form",
                            "explode": False,
                            "schema": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": [
                                        "accepted",
                                        "running",
                                        "successful",
                                        "failed",
                                        "dismissed",
                                    ],
                                },
                            },
                        },
                        {
                            "name": "datetime",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "minDuration",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "minimum": 0},
                        },
                        {
                            "name": "maxDuration",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "minimum": 0},
                        },
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 10000,
                                "default": 10,
                            },
                        },
                    ],
                    "responses": {"200": {"description": "Job list"}},
                }
            },
            "/jobs/{jobId}": {
                "get": {
                    "responses": {
                        "200": {"description": "Job status"},
                        "404": {"description": "Not found"},
                    }
                }
            },
            "/jobs/{jobId}/results": {
                "get": {
                    "responses": {
                        "200": {"description": "Job results"},
                        "404": {"description": "Not ready or not found"},
                        "422": {"description": "Job failed"},
                    }
                }
            },
        },
        "components": {
            "parameters": {
                "collectionId": {
                    "name": "collectionId",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string", "enum": collection_ids},
                }
            }
        },
        "externalDocs": {
            "url": public_url(settings, dataset_api_path(dataset_id, "/"))
        },
    }
