from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request

from gcapi.catalog import CatalogSnapshot, ProcessRoute
from gcapi.config import Settings
from gcapi.problems import problem_response
from gcapi.rewrite import (
    EXECUTE_REL,
    JOB_LIST_REL,
    dataset_api_path,
    public_url,
    rewrite_document,
)
from gcapi.transport import (
    proxy_request,
)

router = APIRouter(tags=["processes"])

IMPORT_PROCESS_ID = "import"
IMPORT_DATASETS = frozenset({"bygning", "fkb_bane"})


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _catalog(request: Request) -> CatalogSnapshot:
    return request.app.state.catalog


def _process_route(
    request: Request, dataset_id: str, process_id: str
) -> ProcessRoute | None:
    return _catalog(request).processes.get(f"{dataset_id}.{process_id}")


def _dataset_exists(request: Request, dataset_id: str) -> bool:
    return dataset_id in _catalog(request).datasets


def _owned_import_description(
    request: Request, dataset_id: str, process_id: str
) -> dict[str, Any]:
    dataset = "FKB-Bane" if dataset_id == "fkb_bane" else "Bygning"
    return {
        "id": process_id,
        "title": f"Import {dataset}",
        "description": f"Upload a multipart JSON-FG or GeoJSON file for asynchronous {dataset} import.",
        "version": "1.0.0",
        "jobControlOptions": ["async-execute"],
        "outputTransmission": ["value"],
        "links": [
            {
                "href": public_url(
                    _settings(request),
                    dataset_api_path(dataset_id, f"/processes/{process_id}"),
                ),
                "rel": "self",
                "type": "application/json",
                "title": "This document",
            },
            {
                "href": public_url(
                    _settings(request),
                    dataset_api_path(dataset_id, f"/processes/{process_id}/execution"),
                ),
                "rel": EXECUTE_REL,
                "type": "multipart/form-data",
                "title": "Execute process",
            },
            {
                "href": public_url(
                    _settings(request),
                    dataset_api_path(
                        dataset_id,
                        f"/jobs?{urlencode({'processID': process_id, 'type': 'process'})}",
                    ),
                ),
                "rel": JOB_LIST_REL,
                "type": "application/json",
                "title": "Jobs for this process",
            },
        ],
        "inputs": {
            "file": {
                "title": "Import file",
                "description": "Uploaded JSON-FG or GeoJSON file.",
                "schema": {
                    "type": "string",
                    "contentEncoding": "binary",
                    "contentMediaType": "application/octet-stream",
                },
            }
        },
        "outputs": {
            "summary": {
                "title": "Import summary",
                "schema": {
                    "type": "object",
                    "properties": {
                        "jobID": {"type": "string"},
                        "processedFeatures": {"type": "integer"},
                        "succeededFeatures": {"type": "integer"},
                        "failedFeatures": {"type": "integer"},
                        "processedBatches": {"type": "integer"},
                        "succeededBatches": {"type": "integer"},
                        "failedBatches": {"type": "integer"},
                        "totalFeatures": {"type": ["integer", "null"]},
                        "completed": {
                            "type": ["string", "null"],
                            "format": "date-time",
                        },
                    },
                },
            }
        },
    }


def _append_job_list_link(
    payload: dict[str, Any], request: Request, dataset_id: str, process_id: str
) -> dict[str, Any]:
    links = payload.get("links")
    job_list_link = {
        "href": public_url(
            _settings(request),
            dataset_api_path(
                dataset_id,
                f"/jobs?{urlencode({'processID': process_id, 'type': 'process'})}",
            ),
        ),
        "rel": JOB_LIST_REL,
        "type": "application/json",
        "title": "Jobs for this process",
    }
    if isinstance(links, list):
        links.append(job_list_link)
    else:
        payload["links"] = [job_list_link]
    return payload


def _canonical_process_document(
    route: ProcessRoute, request: Request
) -> dict[str, Any]:
    payload = deepcopy(route.description)
    payload["id"] = route.local_id
    rewritten = rewrite_document(
        payload,
        settings=_settings(request),
        catalog=_catalog(request),
        upstream_base_url=route.upstream_base_url,
        public_api_base_path=dataset_api_path(route.dataset_id),
    )
    return _append_job_list_link(rewritten, request, route.dataset_id, route.local_id)


@router.get("/datasets/{dataset_id}/ogc_api/processes")
def processes(request: Request, dataset_id: str, limit: int = 10):
    if not _dataset_exists(request, dataset_id):
        return problem_response(
            status_code=404,
            title="Dataset not found",
            detail=f"Unknown dataset '{dataset_id}'",
        )
    settings = _settings(request)
    process_payloads = [
        _canonical_process_document(route, request)
        for route in _catalog(request).processes.values()
        if route.dataset_id == dataset_id
    ]
    if dataset_id in IMPORT_DATASETS:
        process_payloads.append(
            _owned_import_description(request, dataset_id, IMPORT_PROCESS_ID)
        )
    return {
        "processes": process_payloads[: max(1, min(limit, 10000))],
        "links": [
            {
                "href": public_url(
                    settings, dataset_api_path(dataset_id, "/processes")
                ),
                "rel": "self",
                "type": "application/json",
                "title": "This document",
            }
        ],
    }


@router.get("/datasets/{dataset_id}/ogc_api/processes/{process_id}")
def process(request: Request, dataset_id: str, process_id: str):
    if not _dataset_exists(request, dataset_id):
        return problem_response(
            status_code=404,
            title="Dataset not found",
            detail=f"Unknown dataset '{dataset_id}'",
        )
    if dataset_id in IMPORT_DATASETS and process_id == IMPORT_PROCESS_ID:
        return _owned_import_description(request, dataset_id, process_id)
    route = _process_route(request, dataset_id, process_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Process not found",
            detail=f"Unknown process '{process_id}' for dataset '{dataset_id}'",
            type_url="http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-process",
        )
    return _canonical_process_document(route, request)


async def _execute_import_process(request: Request, dataset_id: str, process_id: str):
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        return problem_response(
            status_code=415,
            title="Unsupported media type",
            detail="Import processes require multipart/form-data uploads",
        )
    return await proxy_request(
        client=request.app.state.http_client,
        request=request,
        upstream_url=(
            f"{_settings(request).gcjobs_url}"
            f"{dataset_api_path(dataset_id, f'/processes/{process_id}/execution')}"
        ),
        settings=_settings(request),
        catalog=_catalog(request),
        max_upload_bytes=_settings(request).max_upload_bytes,
        public_api_base_path=dataset_api_path(dataset_id),
    )


@router.post("/datasets/{dataset_id}/ogc_api/processes/{process_id}/execution")
async def execute_process(request: Request, dataset_id: str, process_id: str):
    if not _dataset_exists(request, dataset_id):
        return problem_response(
            status_code=404,
            title="Dataset not found",
            detail=f"Unknown dataset '{dataset_id}'",
        )
    if dataset_id in IMPORT_DATASETS and process_id == IMPORT_PROCESS_ID:
        return await _execute_import_process(request, dataset_id, process_id)
    route = _process_route(request, dataset_id, process_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Process not found",
            detail=f"Unknown process '{process_id}' for dataset '{dataset_id}'",
            type_url="http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-process",
        )
    return await proxy_request(
        client=request.app.state.http_client,
        request=request,
        upstream_url=f"{route.upstream_base_url}/processes/{route.local_id}/execution",
        settings=_settings(request),
        catalog=_catalog(request),
        max_upload_bytes=_settings(request).max_upload_bytes,
        public_api_base_path=dataset_api_path(dataset_id),
    )
