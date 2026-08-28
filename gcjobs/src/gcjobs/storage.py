from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException

from gcjobs import db


@dataclass(frozen=True)
class JobQuery:
    dataset_name: str
    limit: int
    type_values: set[str]
    process_ids: set[str]
    statuses: set[str]
    base_url: str
    public_url: str


@dataclass(frozen=True)
class JobPayloadSettings:
    process_job_type: str
    import_process_id: str
    results_rel: str


def health_status() -> dict[str, object]:
    return db.health_status()


def record_import_event(
    event: dict[str, Any],
    *,
    message_id: str | None = None,
) -> dict[str, Any]:
    return db.record_import_event(event, message_id=message_id)


def record_accepted_import(import_id: str, dataset_name: str) -> dict[str, Any]:
    return record_import_event(
        {
            "import_id": import_id,
            "event": "import.accepted",
            "phase": "accepted",
            "profile": dataset_name,
        }
    )


def record_terminal_event_if_running(import_id: str, event: dict[str, Any]) -> None:
    if _run_is_terminal(db.get_import_run(import_id)):
        return
    record_import_event(event)


def list_dataset_jobs(
    *,
    query: JobQuery,
    settings: JobPayloadSettings,
) -> dict[str, Any]:
    if query.process_ids and settings.import_process_id not in query.process_ids:
        filtered: list[dict[str, Any]] = []
    elif query.type_values and settings.process_job_type not in query.type_values:
        filtered = []
    else:
        jobs = [
            _job_payload(
                run,
                base_url=query.base_url,
                settings=settings,
            )
            for run in db.list_import_runs(active_only=False, limit=10000)
            if _dataset_matches_run(run, query.dataset_name)
        ]
        filtered = _filter_jobs(
            jobs,
            type_values=query.type_values,
            process_ids=query.process_ids,
            statuses=query.statuses,
        )

    return {
        "jobs": filtered[: query.limit],
        "links": [_service_link(query.public_url, "self", "This document")],
    }


def get_dataset_job(
    *,
    dataset_name: str,
    job_id: str,
    base_url: str,
    settings: JobPayloadSettings,
) -> dict[str, Any]:
    run = _run_with_filenames(_require_dataset_run(dataset_name, job_id))
    return _job_payload(
        run,
        base_url=base_url,
        settings=settings,
    )


def get_dataset_job_results(*, dataset_name: str, job_id: str) -> dict[str, Any]:
    run = _run_with_filenames(_require_dataset_run(dataset_name, job_id))
    mapped_status = _map_status(run)
    if mapped_status in {"accepted", "running"}:
        raise HTTPException(status_code=404, detail="job results are not ready")
    if mapped_status == "failed":
        last_error = run.get("last_error")
        detail = "job failed"
        if isinstance(last_error, dict) and isinstance(last_error.get("reason"), str):
            detail = last_error["reason"]
        raise HTTPException(status_code=422, detail=detail)
    return _job_results_payload(run)


def _require_dataset_run(dataset_name: str, job_id: str) -> dict[str, Any]:
    run = db.get_import_run(job_id)
    if run is None or not _dataset_matches_run(run, dataset_name):
        raise HTTPException(status_code=404, detail="job not found")
    return run


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


def _mounted_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


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
    base_url: str,
    path: str,
    rel: str,
    title: str,
    media_type: str = "application/json",
) -> dict[str, str]:
    return _service_link(_mounted_url(base_url, path), rel, title, media_type)


def _job_links(
    run: dict[str, Any],
    *,
    base_url: str,
    results_rel: str,
) -> list[dict[str, str]]:
    job_id = str(run["id"])
    links = [
        _mounted_link(base_url, f"/jobs/{job_id}", "self", "This document"),
        _mounted_link(base_url, "/jobs", "up", "Job list"),
    ]
    if _map_status(run) == "successful":
        links.append(
            _mounted_link(
                base_url,
                f"/jobs/{job_id}/results",
                results_rel,
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


def _run_with_filenames(run: dict[str, Any]) -> dict[str, Any]:
    filenames = _normalized_filenames(run.get("filenames"))
    if filenames is None:
        filenames = _import_filenames(str(run["id"]))
    if filenames is None:
        filenames = _normalized_filenames(run.get("filename"))
    if filenames is None:
        return run
    return {**run, "filenames": filenames}


def _import_filenames(import_id: str) -> list[str] | None:
    for event in db.get_import_events(import_id, limit=5):
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        filenames = _normalized_filenames(payload.get("filenames"))
        if filenames is not None:
            return filenames
        filenames = _normalized_filenames(payload.get("filename"))
        if filenames is not None:
            return filenames
    return None


def _normalized_filenames(value: Any) -> list[str] | None:
    if isinstance(value, str):
        filename = value.strip()
        return [filename] if filename else None
    if not isinstance(value, list):
        return None
    filenames = [
        item.strip() for item in value if isinstance(item, str) and item.strip()
    ]
    return filenames or None


def _job_payload(
    run: dict[str, Any],
    *,
    base_url: str,
    settings: JobPayloadSettings,
) -> dict[str, Any]:
    total_features = run.get("total_features")
    processed_features = int(run.get("processed_features") or 0)
    status = _map_status(run)
    progress = None
    if isinstance(total_features, int) and total_features > 0:
        progress = max(0, min(100, round((processed_features / total_features) * 100)))

    payload: dict[str, Any] = {
        "type": settings.process_job_type,
        "jobID": str(run["id"]),
        "status": status,
        "links": _job_links(
            run,
            base_url=base_url,
            results_rel=settings.results_rel,
        ),
        "updated": _rfc3339_timestamp(run.get("last_event_at")),
        "phase": run.get("phase"),
        "totalFeatures": total_features,
        "processedFeatures": processed_features,
        "succeededFeatures": int(run.get("succeeded_features") or 0),
        "failedFeatures": int(run.get("failed_features") or 0),
        "processedBatches": int(run.get("processed_batches") or 0),
        "succeededBatches": int(run.get("succeeded_batches") or 0),
        "failedBatches": int(run.get("failed_batches") or 0),
        "processID": settings.import_process_id,
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
    filenames = _normalized_filenames(run.get("filenames"))
    if filenames is not None:
        payload["filenames"] = filenames
    payload["message"] = _job_message(status, last_error)
    return payload


def _job_message(status: str, last_error: Any) -> str | None:
    if isinstance(last_error, dict) and isinstance(last_error.get("reason"), str):
        return last_error["reason"]
    return {
        "accepted": "Import accepted",
        "running": "Import running",
        "successful": "Import completed",
    }.get(status)


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
    summary = {
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
    filenames = _normalized_filenames(run.get("filenames"))
    if filenames is not None:
        summary["filenames"] = filenames
    return {"summary": summary}


def _run_is_terminal(run: dict[str, Any] | None) -> bool:
    return run is not None and run.get("status") in {"completed", "failed"}
