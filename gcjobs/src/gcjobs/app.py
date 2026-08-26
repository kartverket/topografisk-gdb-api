from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx2
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gcjobs import config, db
from gcjobs.datasets import (
    DatasetDescription,
    DescriptionError,
    load_dataset_descriptions,
)
from gcjobs.pubsub import ImportEventListener, RedisImportEventListener

# Reuse uvicorn's configured error logger so import-event logs reach the console
# in local/dev runs without additional logging setup.
LOGGER = logging.getLogger("uvicorn.error").getChild("gcjobs.import_events")

IMPORT_CLIENT_TIMEOUT = httpx2.Timeout(5.0, read=None)
PROCESS_JOB_TYPE = "process"
IMPORT_PROCESS_ID = "import"
JOB_LIST_REL = "http://www.opengis.net/def/rel/ogc/1.0/job-list"
RESULTS_REL = "http://www.opengis.net/def/rel/ogc/1.0/results"
PROCESS_EXECUTE_REL = "http://www.opengis.net/def/rel/ogc/1.0/execute"
CONFORMANCE_CLASSES = [
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/json",
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/ogcapi-processes-1/1.0/conf/job-list",
]


@dataclass(frozen=True)
class DatasetMount:
    dataset: DatasetDescription
    mount_path: str
    api_url: str


def _normalize_process_id(process_id: str) -> str:
    normalized = process_id.strip().casefold()
    if normalized != IMPORT_PROCESS_ID:
        raise LookupError(f"processID must be one of: {IMPORT_PROCESS_ID}")
    return normalized


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


def _declared_content_length(headers: Any) -> int | None:
    raw_value = headers.get("content-length")
    if raw_value is None:
        return None

    try:
        value = int(raw_value)
    except ValueError:
        return None

    return value if value >= 0 else None


async def _read_bounded_request_body(request: Request, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total_bytes = 0

    for declared_length in (_declared_content_length(request.headers),):
        if declared_length is not None and declared_length > max_bytes:
            raise HTTPException(status_code=413, detail="upload exceeds size limit")

    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise HTTPException(status_code=413, detail="upload exceeds size limit")
        chunks.append(chunk)

    return b"".join(chunks)


@asynccontextmanager
async def _import_client_context(
    import_client: httpx2.AsyncClient | None,
) -> AsyncIterator[httpx2.AsyncClient]:
    if import_client is not None:
        yield import_client
        return

    # Import execution is proxied synchronously through gcjobs and can take
    # longer than httpx's default read timeout on larger payloads.
    async with httpx2.AsyncClient(
        trust_env=False,
        timeout=IMPORT_CLIENT_TIMEOUT,
    ) as runtime_client:
        yield runtime_client


async def _cancel_proxy_tasks(app_instance: FastAPI) -> None:
    for proxy_task in tuple(app_instance.state.proxy_tasks):
        await _cancel_task(proxy_task)


def _lifespan(
    *,
    event_listener: ImportEventListener | None,
    import_client: httpx2.AsyncClient | None,
):
    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        listener = event_listener or RedisImportEventListener(config.redis_url())
        app_instance.state.proxy_tasks.clear()
        task = asyncio.create_task(_consume_import_events(listener))
        try:
            async with _import_client_context(import_client) as runtime_client:
                app_instance.state.import_client = runtime_client
                yield
        finally:
            await _cancel_proxy_tasks(app_instance)
            await _cancel_task(task)

    return lifespan


async def _cancel_task(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _dataset_matches_run(run: dict[str, Any], dataset_name: str) -> bool:
    profile = run.get("profile")
    return isinstance(profile, str) and profile.casefold() == dataset_name.casefold()


def _map_status(run: dict[str, Any]) -> str:
    status = run.get("status")
    phase = run.get("phase")
    if status == "completed":
        return "successful"
    if status == "failed":
        return "failed"
    if phase in {None, "accepted"}:
        return "accepted"
    return "running"


def _csv_values(raw_value: str | None) -> set[str]:
    if raw_value is None:
        return set()
    return {part.strip() for part in raw_value.split(",") if part.strip()}


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


def _job_links(request: Request, run: dict[str, Any]) -> list[dict[str, str]]:
    job_id = str(run["id"])
    links = [
        _mounted_link(request, f"/jobs/{job_id}", "self", "This document"),
        _mounted_link(request, "/jobs", "up", "Job list"),
    ]
    if _map_status(run) == "successful":
        links.append(
            _mounted_link(
                request,
                f"/jobs/{job_id}/results",
                RESULTS_REL,
                "Job results",
            )
        )
    return links


def _rfc3339_timestamp(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    return None


def _job_payload(request: Request, run: dict[str, Any]) -> dict[str, Any]:
    total_features = run.get("total_features")
    processed_features = int(run.get("processed_features") or 0)
    progress = None
    if isinstance(total_features, int) and total_features > 0:
        progress = max(0, min(100, round((processed_features / total_features) * 100)))

    payload: dict[str, Any] = {
        "type": PROCESS_JOB_TYPE,
        "jobID": str(run["id"]),
        "status": _map_status(run),
        "links": _job_links(request, run),
        "updated": _rfc3339_timestamp(run.get("last_event_at")),
        "phase": run.get("phase"),
        "totalFeatures": run.get("total_features"),
        "processedFeatures": processed_features,
        "succeededFeatures": int(run.get("succeeded_features") or 0),
        "failedFeatures": int(run.get("failed_features") or 0),
        "processedBatches": int(run.get("processed_batches") or 0),
        "succeededBatches": int(run.get("succeeded_batches") or 0),
        "failedBatches": int(run.get("failed_batches") or 0),
        "processID": IMPORT_PROCESS_ID,
    }
    if progress is not None:
        payload["progress"] = progress
    created_at = _rfc3339_timestamp(run.get("started_at"))
    if created_at is not None:
        payload["created"] = created_at
        if run.get("phase") not in {None, "accepted"}:
            payload["started"] = created_at
    finished_at = _rfc3339_timestamp(run.get("completed_at"))
    if finished_at is not None:
        payload["finished"] = finished_at
    last_error = run.get("last_error")
    if isinstance(last_error, dict):
        payload["lastError"] = last_error
    if isinstance(last_error, dict) and isinstance(last_error.get("reason"), str):
        payload["message"] = last_error["reason"]
    elif payload["status"] == "accepted":
        payload["message"] = "Import accepted"
    elif payload["status"] == "running":
        payload["message"] = "Import running"
    elif payload["status"] == "successful":
        payload["message"] = "Import completed"
    return payload


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


async def _queue_import_request(
    request: Request,
    import_client: httpx2.AsyncClient,
    dataset_name: str,
) -> str:
    payload = await _read_bounded_request_body(request, config.max_upload_bytes())
    import_id = str(uuid4())
    content_type = request.headers.get("content-type", "application/octet-stream")

    db.record_import_event(
        {
            "import_id": import_id,
            "event": "import.accepted",
            "phase": "accepted",
            "profile": dataset_name,
        }
    )

    proxy_task = asyncio.create_task(
        _proxy_import(
            import_client,
            import_id,
            dataset_name,
            content_type,
            payload,
        )
    )
    root_app = getattr(request.app.state, "root_app", request.app)
    proxy_tasks = root_app.state.proxy_tasks
    proxy_tasks.add(proxy_task)
    proxy_task.add_done_callback(proxy_tasks.discard)
    return import_id


def _filter_jobs(
    jobs: list[dict[str, Any]],
    *,
    type_values: set[str],
    process_ids: set[str],
    statuses: set[str],
) -> list[dict[str, Any]]:
    filtered = jobs
    if type_values:
        filtered = [job for job in filtered if job.get("type") in type_values]
    if process_ids:
        filtered = [job for job in filtered if job.get("processID") in process_ids]
    if statuses:
        filtered = [job for job in filtered if job.get("status") in statuses]
    return filtered


def _job_results_payload(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": {
            "jobID": str(run["id"]),
            "processedFeatures": run.get("processed_features"),
            "succeededFeatures": run.get("succeeded_features"),
            "failedFeatures": run.get("failed_features"),
            "processedBatches": run.get("processed_batches"),
            "succeededBatches": run.get("succeeded_batches"),
            "failedBatches": run.get("failed_batches"),
            "totalFeatures": run.get("total_features"),
            "completed": run.get("completed_at"),
        }
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
                "/conformance",
                "conformance",
                "Conformance classes",
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


def _conformance_payload(request: Request) -> dict[str, Any]:
    return {
        "conformsTo": CONFORMANCE_CLASSES,
        "links": [_mounted_link(request, "/conformance", "self", "This document")],
    }


def _collections_payload(request: Request) -> dict[str, Any]:
    return {
        "collections": [],
        "links": [_mounted_link(request, "/collections", "self", "This document")],
    }


def _processes_payload(request: Request, dataset: DatasetDescription) -> dict[str, Any]:
    processes = [_process_payload(request, dataset)] if dataset.import_enabled else []
    return {
        "processes": processes,
        "links": [_mounted_link(request, "/processes", "self", "This document")],
    }


def _build_dataset_app(
    root_app: FastAPI,
    dataset: DatasetDescription,
    api_url: str,
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

    @dataset_app.get("/conformance")
    def conformance(request: Request) -> dict[str, Any]:
        return _conformance_payload(request)

    @dataset_app.get("/collections")
    @dataset_app.get("/collections/{collection_id}")
    def collections(
        request: Request, collection_id: str | None = None
    ) -> dict[str, Any]:
        if collection_id is not None:
            raise HTTPException(status_code=404, detail="collection not found")
        return _collections_payload(request)

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

        import_id = await _queue_import_request(
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
        type_filter = _csv_values(type_values)
        process_filter = _csv_values(process_id)
        if process_filter and IMPORT_PROCESS_ID not in process_filter:
            filtered: list[dict[str, Any]] = []
        elif type_filter and PROCESS_JOB_TYPE not in type_filter:
            filtered = []
        else:
            jobs_list = [
                _job_payload(request, run)
                for run in db.list_import_runs(active_only=False, limit=10000)
                if _dataset_matches_run(run, dataset.name)
            ]
            filtered = _filter_jobs(
                jobs_list,
                type_values=type_filter,
                process_ids=process_filter,
                statuses=_csv_values(status),
            )

        return {
            "jobs": filtered[:limit],
            "links": [
                _service_link(
                    _public_request_url(request),
                    "self",
                    "This document",
                )
            ],
        }

    @dataset_app.get("/jobs/{job_id}", name="dataset_job")
    def job(request: Request, job_id: str) -> dict[str, Any]:
        run = db.get_import_run(job_id)
        if run is None or not _dataset_matches_run(run, dataset.name):
            raise HTTPException(status_code=404, detail="job not found")
        return _job_payload(request, run)

    @dataset_app.get("/jobs/{job_id}/results", name="dataset_job_results")
    def job_results(job_id: str) -> dict[str, Any]:
        run = db.get_import_run(job_id)
        if run is None or not _dataset_matches_run(run, dataset.name):
            raise HTTPException(status_code=404, detail="job not found")

        mapped_status = _map_status(run)
        if mapped_status in {"accepted", "running"}:
            raise HTTPException(status_code=404, detail="job results are not ready")
        if mapped_status == "failed":
            last_error = run.get("last_error")
            detail = "job failed"
            if isinstance(last_error, dict) and isinstance(
                last_error.get("reason"), str
            ):
                detail = last_error["reason"]
            raise HTTPException(status_code=422, detail=detail)
        return _job_results_payload(run)

    return dataset_app


def _register_routes(application: FastAPI, mounts: list[DatasetMount]) -> None:
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
            payload.update(db.health_status())
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


def create_app(
    *,
    event_listener: ImportEventListener | None = None,
    import_client: httpx2.AsyncClient | None = None,
) -> FastAPI:
    try:
        datasets = load_dataset_descriptions(
            config.descriptions_dir(),
            supported_import_profiles=config.SUPPORTED_IMPORT_PROFILES,
        )
    except DescriptionError as err:
        raise RuntimeError(f"invalid shared descriptions for gcjobs: {err}") from err

    application = FastAPI(
        title="gcjobs",
        version="0.1.0",
        lifespan=_lifespan(
            event_listener=event_listener,
            import_client=import_client,
        ),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.state.proxy_tasks = set()

    mounts: list[DatasetMount] = []
    for dataset in datasets:
        path = mount_path(dataset.name)
        api_url = f"{config.api_base_url()}{path}"
        application.mount(path, _build_dataset_app(application, dataset, api_url))
        mounts.append(DatasetMount(dataset, path, api_url))

    _register_routes(application, mounts)

    return application


async def _proxy_import(
    import_client: httpx2.AsyncClient,
    import_id: str,
    profile_name: str,
    content_type: str,
    payload: bytes,
) -> None:
    try:
        response = await import_client.post(
            f"{config.gcimport_api_url()}/imports",
            params={"profile": profile_name},
            headers={
                "X-Import-Id": import_id,
                "Content-Type": content_type,
            },
            content=payload,
        )
        response.raise_for_status()
    except httpx2.HTTPError as err:
        _record_proxy_terminal_event(
            import_id,
            {
                "import_id": import_id,
                "event": "import.completed.failed",
                "phase": "forwarding",
                "profile": profile_name,
                "reason": f"gcjobs could not reach gcimport: {err}",
            },
        )
        LOGGER.exception("Import proxy failed", extra={"import_id": import_id})
        return


def _record_proxy_terminal_event(import_id: str, event: dict[str, Any]) -> None:
    if _run_is_terminal(db.get_import_run(import_id)):
        return
    db.record_import_event(event)


def _run_is_terminal(run: dict[str, Any] | None) -> bool:
    return run is not None and run.get("status") in {"completed", "failed"}


async def _consume_import_events(listener: ImportEventListener) -> None:
    try:
        async for message in listener.messages():
            db.record_import_event(message.event, message_id=message.message_id)
            await message.ack()
            LOGGER.info("import event %s", _event_for_log(message.event))
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGGER.exception("Import event listener stopped")


def _event_for_log(event: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(event)
    feature_ids = sanitized.pop("feature_ids", None)
    if isinstance(feature_ids, list):
        sanitized["feature_id_count"] = len(feature_ids)
    return sanitized


app = create_app()
