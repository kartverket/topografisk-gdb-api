from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request

from gcapi.catalog import CatalogSnapshot, ProcessRoute
from gcapi.config import Settings
from gcapi.problems import problem_response
from gcapi.rewrite import EXECUTE_REL, JOB_LIST_REL, public_url, rewrite_document
from gcapi.transport import (
    proxy_request,
)

router = APIRouter(tags=["processes"])

IMPORT_PROCESS_IDS = {
    "import-fkb-bane": "fkb_bane",
    "import-bygning": "bygning",
}


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _catalog(request: Request) -> CatalogSnapshot:
    return request.app.state.catalog


def _process_route(request: Request, process_id: str) -> ProcessRoute | None:
    return _catalog(request).processes.get(process_id)


def _owned_import_description(request: Request, process_id: str) -> dict[str, Any]:
    title = "Import FKB-Bane" if process_id == "import-fkb-bane" else "Import Bygning"
    dataset = "FKB-Bane" if process_id == "import-fkb-bane" else "Bygning"
    return {
        "id": process_id,
        "title": title,
        "description": f"Upload a multipart JSON-FG or GeoJSON file for asynchronous {dataset} import.",
        "version": "1.0.0",
        "jobControlOptions": ["async-execute"],
        "outputTransmission": ["value"],
        "links": [
            {
                "href": public_url(_settings(request), f"/processes/{process_id}"),
                "rel": "self",
                "type": "application/json",
                "title": "This document",
            },
            {
                "href": public_url(
                    _settings(request), f"/processes/{process_id}/execution"
                ),
                "rel": EXECUTE_REL,
                "type": "multipart/form-data",
                "title": "Execute process",
            },
            {
                "href": public_url(
                    _settings(request),
                    f"/jobs?{urlencode({'processID': process_id, 'type': 'process'})}",
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
    payload: dict[str, Any], request: Request, process_id: str
) -> dict[str, Any]:
    links = payload.get("links")
    job_list_link = {
        "href": public_url(
            _settings(request),
            f"/jobs?{urlencode({'processID': process_id, 'type': 'process'})}",
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
    payload["id"] = route.public_id
    rewritten = rewrite_document(
        payload,
        settings=_settings(request),
        catalog=_catalog(request),
        upstream_base_url=route.upstream_base_url,
    )
    return _append_job_list_link(rewritten, request, route.public_id)


@router.get("/processes")
def processes(request: Request, limit: int = 10) -> dict[str, Any]:
    settings = _settings(request)
    process_payloads = [
        _canonical_process_document(route, request)
        for route in _catalog(request).processes.values()
    ]
    process_payloads.extend(
        [
            _owned_import_description(request, process_id)
            for process_id in IMPORT_PROCESS_IDS
        ]
    )
    return {
        "processes": process_payloads[: max(1, min(limit, 10000))],
        "links": [
            {
                "href": public_url(settings, "/processes"),
                "rel": "self",
                "type": "application/json",
                "title": "This document",
            }
        ],
    }


@router.get("/processes/{process_id}")
def process(request: Request, process_id: str):
    if process_id in IMPORT_PROCESS_IDS:
        return _owned_import_description(request, process_id)
    route = _process_route(request, process_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Process not found",
            detail=f"Unknown process '{process_id}'",
            type_url="http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-process",
        )
    return _canonical_process_document(route, request)


async def _execute_import_process(request: Request, process_id: str):
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
        upstream_url=f"{_settings(request).gcjobs_url}/processes/{process_id}/execution",
        settings=_settings(request),
        catalog=_catalog(request),
        max_upload_bytes=_settings(request).max_upload_bytes,
    )


@router.post("/processes/{process_id}/execution")
async def execute_process(request: Request, process_id: str):
    if process_id in IMPORT_PROCESS_IDS:
        return await _execute_import_process(request, process_id)
    route = _process_route(request, process_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Process not found",
            detail=f"Unknown process '{process_id}'",
            type_url="http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-process",
        )
    return await proxy_request(
        client=request.app.state.http_client,
        request=request,
        upstream_url=f"{route.upstream_base_url}/processes/{route.local_id}/execution",
        settings=_settings(request),
        catalog=_catalog(request),
        max_upload_bytes=_settings(request).max_upload_bytes,
    )
