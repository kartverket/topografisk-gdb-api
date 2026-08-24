from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any
from uuid import uuid4

import httpx2
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gcjobs import config, db
from gcjobs.pubsub import ImportEventListener, RedisImportEventListener

# Reuse uvicorn's configured error logger so import-event logs reach the console
# in local/dev runs without additional logging setup.
LOGGER = logging.getLogger("uvicorn.error").getChild("gcjobs.import_events")

IMPORT_CLIENT_TIMEOUT = httpx2.Timeout(5.0, read=None)
IMPORT_PROCESS_IDS = {
    "import-bygning": "bygning",
    "import-fkb-bane": "fkb_bane",
}
PROCESS_IDS_BY_PROFILE = {
    profile_name: process_id for process_id, profile_name in IMPORT_PROCESS_IDS.items()
}
PROCESS_JOB_TYPE = "process"
JOB_LIST_REL = "http://www.opengis.net/def/rel/ogc/1.0/job-list"
RESULTS_REL = "http://www.opengis.net/def/rel/ogc/1.0/results"
EXECUTE_REL = "http://www.opengis.net/def/rel/ogc/1.0/execute"


def _supported_processes_detail() -> str:
    supported = ", ".join(sorted(IMPORT_PROCESS_IDS))
    return f"processID must be one of: {supported}"


def _normalize_process_id(process_id: str) -> str:
    normalized = process_id.strip().casefold()
    if normalized not in IMPORT_PROCESS_IDS:
        raise HTTPException(status_code=404, detail=_supported_processes_detail())
    return normalized


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


def _lifespan(
    *,
    event_listener: ImportEventListener | None,
    import_client: httpx2.AsyncClient | None,
):
    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        listener = event_listener or RedisImportEventListener(config.redis_url())
        task = asyncio.create_task(_consume_import_events(listener))
        if import_client is not None:
            app_instance.state.import_client = import_client
            try:
                yield
            finally:
                await _cancel_task(task)
            return

        # Import execution is proxied synchronously through gcjobs and can take
        # longer than httpx's default read timeout on larger payloads.
        async with httpx2.AsyncClient(
            trust_env=False,
            timeout=IMPORT_CLIENT_TIMEOUT,
        ) as runtime_client:
            app_instance.state.import_client = runtime_client
            try:
                yield
            finally:
                await _cancel_task(task)

    return lifespan


async def _cancel_task(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


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


def _job_url(request: Request, path: str) -> str:
    return f"{str(request.base_url).rstrip('/')}{path}"


def _process_url(request: Request, process_id: str) -> str:
    return _job_url(request, f"/processes/{process_id}")


def _job_links(request: Request, run: dict[str, Any]) -> list[dict[str, str]]:
    job_id = str(run["id"])
    links = [
        {
            "href": _job_url(request, f"/jobs/{job_id}"),
            "rel": "self",
            "type": "application/json",
            "title": "This document",
        },
        {
            "href": _job_url(request, "/jobs"),
            "rel": "up",
            "type": "application/json",
            "title": "Job list",
        },
    ]
    if _map_status(run) == "successful":
        links.append(
            {
                "href": _job_url(request, f"/jobs/{job_id}/results"),
                "rel": RESULTS_REL,
                "type": "application/json",
                "title": "Job results",
            }
        )
    return links


def _job_payload(request: Request, run: dict[str, Any]) -> dict[str, Any]:
    total_features = run.get("total_features")
    processed_features = int(run.get("processed_features") or 0)
    progress = None
    if isinstance(total_features, int) and total_features > 0:
        progress = max(0, min(100, round((processed_features / total_features) * 100)))

    profile_name = run.get("profile")
    payload: dict[str, Any] = {
        "type": PROCESS_JOB_TYPE,
        "jobID": str(run["id"]),
        "status": _map_status(run),
        "links": _job_links(request, run),
        "updated": run.get("last_event_at"),
        "phase": run.get("phase"),
        "totalFeatures": run.get("total_features"),
        "processedFeatures": processed_features,
        "succeededFeatures": int(run.get("succeeded_features") or 0),
        "failedFeatures": int(run.get("failed_features") or 0),
        "processedBatches": int(run.get("processed_batches") or 0),
        "succeededBatches": int(run.get("succeeded_batches") or 0),
        "failedBatches": int(run.get("failed_batches") or 0),
    }
    if isinstance(profile_name, str) and profile_name in PROCESS_IDS_BY_PROFILE:
        payload["processID"] = PROCESS_IDS_BY_PROFILE[profile_name]
    if progress is not None:
        payload["progress"] = progress
    if isinstance(run.get("started_at"), str):
        payload["created"] = run["started_at"]
        if run.get("phase") not in {None, "accepted"}:
            payload["started"] = run["started_at"]
    if isinstance(run.get("completed_at"), str):
        payload["finished"] = run["completed_at"]
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
            {
                "href": _job_url(request, f"/jobs/{import_id}"),
                "rel": "self",
                "type": "application/json",
                "title": "This document",
            },
            {
                "href": _job_url(request, "/jobs"),
                "rel": "up",
                "type": "application/json",
                "title": "Job list",
            },
        ],
    }


def _process_payload(request: Request, process_id: str) -> dict[str, Any]:
    return {
        "id": process_id,
        "title": f"Import {IMPORT_PROCESS_IDS[process_id]}",
        "description": f"Asynchronously import data using the {IMPORT_PROCESS_IDS[process_id]} profile.",
        "jobControlOptions": ["async-execute"],
        "links": [
            {
                "href": _process_url(request, process_id),
                "rel": "self",
                "type": "application/json",
                "title": "This process",
            },
            {
                "href": _job_url(request, f"/processes/{process_id}/execution"),
                "rel": EXECUTE_REL,
                "type": "multipart/form-data",
                "title": "Execute process",
            },
            {
                "href": _job_url(request, f"/jobs?type=process&processID={process_id}"),
                "rel": JOB_LIST_REL,
                "type": "application/json",
                "title": "Process jobs",
            },
        ],
    }


async def _queue_import_request(
    application: FastAPI,
    background_tasks: BackgroundTasks,
    request: Request,
    profile_name: str,
) -> str:
    payload = await _read_bounded_request_body(request, config.max_upload_bytes())
    import_id = str(uuid4())
    content_type = request.headers.get("content-type", "application/octet-stream")

    db.record_import_event(
        {
            "import_id": import_id,
            "event": "import.accepted",
            "phase": "accepted",
            "profile": profile_name,
        }
    )

    background_tasks.add_task(
        _proxy_import,
        application.state.import_client,
        import_id,
        profile_name,
        content_type,
        payload,
    )
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


def _register_routes(application: FastAPI) -> None:
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

    @application.get("/processes")
    def processes(request: Request) -> dict[str, Any]:
        return {
            "processes": [
                _process_payload(request, process_id)
                for process_id in sorted(IMPORT_PROCESS_IDS)
            ],
            "links": [
                {
                    "href": _job_url(request, "/processes"),
                    "rel": "self",
                    "type": "application/json",
                    "title": "This document",
                }
            ],
        }

    @application.get("/processes/{process_id}")
    def process(request: Request, process_id: str) -> dict[str, Any]:
        return _process_payload(request, _normalize_process_id(process_id))

    @application.post("/processes/{process_id}/execution")
    async def execute_process(
        background_tasks: BackgroundTasks,
        request: Request,
        process_id: str,
    ) -> JSONResponse:
        normalized_process_id = _normalize_process_id(process_id)
        content_type = request.headers.get("content-type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise HTTPException(
                status_code=415,
                detail="Import processes require multipart/form-data uploads",
            )
        profile_name = IMPORT_PROCESS_IDS[normalized_process_id]
        import_id = await _queue_import_request(
            application,
            background_tasks,
            request,
            profile_name,
        )
        location = _job_url(request, f"/jobs/{import_id}")
        return JSONResponse(
            _accepted_job_payload(request, import_id, normalized_process_id),
            status_code=201,
            headers={"Location": location},
        )

    @application.get("/jobs")
    def jobs(
        request: Request,
        limit: int = Query(default=10, ge=1, le=10000),
        type_values: str | None = Query(default=None, alias="type"),
        status: str | None = None,
        process_id: str | None = Query(default=None, alias="processID"),
    ) -> dict[str, Any]:
        jobs_list = [
            _job_payload(request, run)
            for run in db.list_import_runs(active_only=False, limit=10000)
        ]
        type_filter = _csv_values(type_values)
        if type_filter and PROCESS_JOB_TYPE not in type_filter:
            filtered: list[dict[str, Any]] = []
        else:
            filtered = _filter_jobs(
                jobs_list,
                type_values=type_filter,
                process_ids=_csv_values(process_id),
                statuses=_csv_values(status),
            )
        return {
            "jobs": filtered[:limit],
            "links": [
                {
                    "href": str(request.url),
                    "rel": "self",
                    "type": "application/json",
                    "title": "This document",
                }
            ],
        }

    @application.get("/jobs/{job_id}")
    def job(request: Request, job_id: str) -> dict[str, Any]:
        run = db.get_import_run(job_id)
        if run is None:
            raise HTTPException(status_code=404, detail="job not found")
        return _job_payload(request, run)

    @application.get("/jobs/{job_id}/results")
    def job_results(job_id: str) -> dict[str, Any]:
        run = db.get_import_run(job_id)
        if run is None:
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


def create_app(
    *,
    event_listener: ImportEventListener | None = None,
    import_client: httpx2.AsyncClient | None = None,
) -> FastAPI:
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

    _register_routes(application)

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
