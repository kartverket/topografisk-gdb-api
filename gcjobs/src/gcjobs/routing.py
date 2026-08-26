from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx2
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from gcjobs import config, storage
from gcjobs.datasets import DatasetDescription

PROCESS_JOB_TYPE = "process"
IMPORT_PROCESS_ID = "import"
JOB_LIST_REL = "http://www.opengis.net/def/rel/ogc/1.0/job-list"
RESULTS_REL = "http://www.opengis.net/def/rel/ogc/1.0/results"
PROCESS_EXECUTE_REL = "http://www.opengis.net/def/rel/ogc/1.0/execute"
JOB_PAYLOAD_SETTINGS = storage.JobPayloadSettings(
    process_job_type=PROCESS_JOB_TYPE,
    import_process_id=IMPORT_PROCESS_ID,
    results_rel=RESULTS_REL,
)


@dataclass(frozen=True)
class DatasetMount:
    dataset: DatasetDescription
    mount_path: str
    api_url: str


def mount_path(dataset_name: str) -> str:
    return f"/datasets/{dataset_name}/ogc_api"


def dataset_index(mounts: list[DatasetMount]) -> dict[str, Any]:
    return {
        "title": "gcjobs datasets",
        "description": "Each dataset is served as its own OGC API for import jobs.",
        "datasets": [
            {
                "id": mount.dataset.name,
                "title": mount.dataset.title,
                "description": mount.dataset.description,
                "processes": [IMPORT_PROCESS_ID]
                if mount.dataset.import_enabled
                else [],
                "links": [
                    {
                        "rel": "service-desc",
                        "type": "application/json",
                        "title": f"OGC API for '{mount.dataset.name}'",
                        "href": mount.api_url + "/",
                    }
                ],
            }
            for mount in mounts
        ],
    }


def register_routes(application: FastAPI, mounts: list[DatasetMount]) -> None:
    @application.get("/")
    def root() -> dict[str, str]:
        return {"service": config.SERVICE_NAME, "schema": config.DB_SCHEMA}

    @application.get("/healthz")
    def healthz() -> dict[str, object]:
        payload: dict[str, object] = {
            "status": "ok",
            "service": config.SERVICE_NAME,
            "schema": config.DB_SCHEMA,
        }
        try:
            payload.update(storage.health_status())
        except RuntimeError as err:
            payload["status"] = "misconfigured"
            payload["detail"] = str(err)
            return JSONResponse(payload, status_code=503)
        except Exception:
            payload["status"] = "unavailable"
            return JSONResponse(payload, status_code=503)
        return payload

    @application.get("/datasets")
    def datasets() -> dict[str, Any]:
        return dataset_index(mounts)


def build_dataset_app(
    root_app: FastAPI,
    dataset: DatasetDescription,
    api_url: str,
    *,
    queue_import_request: Callable[[Request, httpx2.AsyncClient, str], Awaitable[str]],
) -> FastAPI:
    dataset_app = FastAPI(
        title=f"gcjobs {dataset.name}",
        description=dataset.description or dataset.title,
        version="0.1.0",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    dataset_app.state.api_url = api_url.rstrip("/")
    dataset_app.state.root_app = root_app
    dataset_app.state.dataset = dataset

    @dataset_app.get("/")
    def landing(request: Request) -> dict[str, Any]:
        return _landing_payload(request, dataset)

    @dataset_app.get("/openapi")
    def openapi() -> dict[str, Any]:
        return dataset_app.openapi()

    @dataset_app.get("/processes", name="dataset_processes")
    @dataset_app.get("/processes/{process_id}", name="dataset_process")
    def processes(request: Request, process_id: str | None = None) -> dict[str, Any]:
        if process_id is None:
            return _processes_payload(request, dataset)
        if not dataset.import_enabled or process_id.casefold() != IMPORT_PROCESS_ID:
            raise HTTPException(status_code=404, detail="process not found")
        return _process_payload(request, dataset)

    @dataset_app.post(
        "/processes/{process_id}/execution",
        name="dataset_process_execution",
    )
    async def execute_process(request: Request, process_id: str) -> JSONResponse:
        if not dataset.import_enabled:
            return JSONResponse({"detail": "process not found"}, status_code=404)
        try:
            normalized_process_id = _normalize_process_id(process_id)
        except LookupError as err:
            return JSONResponse({"detail": str(err)}, status_code=404)

        content_type = request.headers.get("content-type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            return JSONResponse(
                {"detail": "Import processes require multipart/form-data uploads"},
                status_code=415,
            )

        import_id = await queue_import_request(
            request,
            dataset_app.state.root_app.state.import_client,
            dataset.name,
        )
        location = _mounted_url(request, f"/jobs/{import_id}")
        return JSONResponse(
            _accepted_job_payload(request, import_id, normalized_process_id),
            status_code=201,
            headers={"Location": location},
        )

    @dataset_app.get("/jobs", name="dataset_jobs")
    def jobs(
        request: Request,
        limit: int = Query(default=10, ge=1, le=10000),
        type_values: str | None = Query(default=None, alias="type"),
        status: str | None = None,
        process_id: str | None = Query(default=None, alias="processID"),
    ) -> dict[str, Any]:
        return storage.list_dataset_jobs(
            query=storage.JobQuery(
                dataset_name=dataset.name,
                limit=limit,
                type_values=_csv_values(type_values),
                process_ids=_csv_values(process_id),
                statuses=_csv_values(status),
                base_url=_mounted_base_url(request),
                public_url=_public_request_url(request),
            ),
            settings=JOB_PAYLOAD_SETTINGS,
        )

    @dataset_app.get("/jobs/{job_id}", name="dataset_job")
    def job(request: Request, job_id: str) -> dict[str, Any]:
        return storage.get_dataset_job(
            dataset_name=dataset.name,
            job_id=job_id,
            base_url=_mounted_base_url(request),
            settings=JOB_PAYLOAD_SETTINGS,
        )

    @dataset_app.get("/jobs/{job_id}/results", name="dataset_job_results")
    def job_results(job_id: str) -> dict[str, Any]:
        return storage.get_dataset_job_results(
            dataset_name=dataset.name,
            job_id=job_id,
        )

    return dataset_app


def _normalize_process_id(process_id: str) -> str:
    normalized = process_id.strip().casefold()
    if normalized != IMPORT_PROCESS_ID:
        raise LookupError(f"processID must be one of: {IMPORT_PROCESS_ID}")
    return normalized


def _csv_values(raw_value: str | None) -> set[str]:
    if raw_value is None:
        return set()
    return {part.strip() for part in raw_value.split(",") if part.strip()}


def _service_link(
    href: str,
    rel: str,
    title: str,
    media_type: str = "application/json",
) -> dict[str, str]:
    return {
        "href": href,
        "rel": rel,
        "type": media_type,
        "title": title,
    }


def _mounted_link(
    request: Request,
    path: str,
    rel: str,
    title: str,
    media_type: str = "application/json",
) -> dict[str, str]:
    return _service_link(_mounted_url(request, path), rel, title, media_type)


def _mounted_base_url(request: Request) -> str:
    return str(request.app.state.api_url).rstrip("/")


def _public_request_url(request: Request) -> str:
    root_path = str(request.scope.get("root_path", "")).rstrip("/")
    path = str(request.scope.get("path", ""))
    if root_path and path.startswith(root_path):
        path = path[len(root_path) :] or "/"
    query = request.url.query
    url = f"{_mounted_base_url(request)}{path}"
    if query:
        return f"{url}?{query}"
    return url


def _mounted_url(request: Request, path: str) -> str:
    return f"{_mounted_base_url(request)}{path}"


def _accepted_job_payload(
    request: Request, import_id: str, process_id: str
) -> dict[str, Any]:
    return {
        "type": PROCESS_JOB_TYPE,
        "jobID": import_id,
        "processID": process_id,
        "status": "accepted",
        "message": "Import accepted",
        "links": [
            _mounted_link(request, f"/jobs/{import_id}", "self", "This document"),
            _mounted_link(request, "/jobs", "up", "Job list"),
        ],
    }


def _process_payload(request: Request, dataset: DatasetDescription) -> dict[str, Any]:
    return {
        "id": IMPORT_PROCESS_ID,
        "title": f"Import {dataset.title}",
        "description": f"Asynchronously import data into the {dataset.title} dataset.",
        "jobControlOptions": ["async-execute"],
        "links": [
            _mounted_link(
                request,
                f"/processes/{IMPORT_PROCESS_ID}",
                "self",
                "This process",
            ),
            _mounted_link(
                request,
                f"/processes/{IMPORT_PROCESS_ID}/execution",
                PROCESS_EXECUTE_REL,
                "Execute process",
                "multipart/form-data",
            ),
            {
                "href": _mounted_url(request, "/jobs")
                + f"?type=process&processID={IMPORT_PROCESS_ID}",
                "rel": JOB_LIST_REL,
                "type": "application/json",
                "title": "Process jobs",
            },
        ],
    }


def _landing_payload(request: Request, dataset: DatasetDescription) -> dict[str, Any]:
    return {
        "title": dataset.title,
        "description": dataset.description or dataset.title,
        "links": [
            _mounted_link(request, "/", "self", "This document"),
            _mounted_link(
                request,
                "/openapi",
                "service-desc",
                "OpenAPI definition",
            ),
            _mounted_link(
                request,
                "/processes",
                "http://www.opengis.net/def/rel/ogc/1.0/processes",
                "Processes",
            ),
            _mounted_link(
                request,
                "/jobs",
                JOB_LIST_REL,
                "Jobs",
            ),
        ],
    }


def _processes_payload(request: Request, dataset: DatasetDescription) -> dict[str, Any]:
    processes = [_process_payload(request, dataset)] if dataset.import_enabled else []
    return {
        "processes": processes,
        "links": [_mounted_link(request, "/processes", "self", "This document")],
    }
