from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Query, Request

from gcapi.catalog import CatalogSnapshot
from gcapi.config import Settings
from gcapi.problems import problem_response
from gcapi.rewrite import rewrite_document
from gcapi.transport import proxy_request

router = APIRouter(tags=["jobs"])

PROCESS_JOB_TYPE = "process"


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _catalog(request: Request) -> CatalogSnapshot:
    return request.app.state.catalog


def _csv_values(raw_value: str | None) -> set[str]:
    if raw_value is None:
        return set()
    return {part.strip() for part in raw_value.split(",") if part.strip()}


def _parse_rfc3339(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _created_in_range(created: datetime | None, datetime_filter: str) -> bool:
    if created is None:
        return False
    if "/" not in datetime_filter:
        target = _parse_rfc3339(datetime_filter)
        if target is None:
            raise ValueError("datetime must be an RFC 3339 timestamp or interval")
        return created == target

    start_raw, end_raw = datetime_filter.split("/", 1)
    start = None if start_raw in {"", ".."} else _parse_rfc3339(start_raw)
    end = None if end_raw in {"", ".."} else _parse_rfc3339(end_raw)
    if (start_raw not in {"", ".."} and start is None) or (
        end_raw not in {"", ".."} and end is None
    ):
        raise ValueError("datetime must be an RFC 3339 timestamp or interval")
    if start is not None and created < start:
        return False
    return not (end is not None and created > end)


def _duration_seconds(job: dict[str, Any], now: datetime) -> int | None:
    started = _parse_rfc3339(job.get("started"))
    if started is None:
        return None
    status = job.get("status")
    if status == "running":
        return max(0, int((now - started).total_seconds()))
    if status in {"successful", "failed", "dismissed"}:
        finished = _parse_rfc3339(job.get("finished"))
        if finished is None:
            return None
        return max(0, int((finished - started).total_seconds()))
    return None


def _filter_jobs(  # noqa: PLR0913
    jobs: list[dict[str, Any]],
    *,
    type_values: set[str],
    process_ids: set[str],
    statuses: set[str],
    datetime_filter: str | None,
    min_duration: int | None,
    max_duration: int | None,
) -> list[dict[str, Any]]:
    filtered = jobs
    if type_values:
        filtered = [job for job in filtered if job.get("type") in type_values]
    if process_ids:
        filtered = [job for job in filtered if job.get("processID") in process_ids]
    if statuses:
        filtered = [job for job in filtered if job.get("status") in statuses]
    if datetime_filter is not None:
        filtered = [
            job
            for job in filtered
            if _created_in_range(_parse_rfc3339(job.get("created")), datetime_filter)
        ]
    if min_duration is not None or max_duration is not None:
        now = datetime.now(UTC)
        duration_filtered: list[dict[str, Any]] = []
        for job in filtered:
            duration = _duration_seconds(job, now)
            if duration is None:
                continue
            if min_duration is not None and duration < min_duration:
                continue
            if max_duration is not None and duration > max_duration:
                continue
            duration_filtered.append(job)
        filtered = duration_filtered
    return filtered


async def _gcjobs_jobs(request: Request) -> list[dict[str, Any]] | Any:
    upstream_url = f"{_settings(request).gcjobs_url}/jobs"
    try:
        response = await request.app.state.http_client.get(
            upstream_url, params={"limit": 10000}
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as err:
        return problem_response(
            status_code=502,
            title="Upstream error",
            detail=f"gcjobs returned an error for {upstream_url}: {err}",
        )
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        return problem_response(
            status_code=502,
            title="Malformed upstream response",
            detail="gcjobs jobs endpoint did not return a jobs list",
        )
    return [
        rewrite_document(
            job,
            settings=_settings(request),
            catalog=_catalog(request),
            upstream_base_url=upstream_url,
        )
        for job in jobs
        if isinstance(job, dict)
    ]


@router.get("/jobs")
async def jobs(  # noqa: PLR0913, PLR0917
    request: Request,
    limit: int = 10,
    type_values: str | None = Query(default=None, alias="type"),
    status: str | None = None,
    process_id: str | None = Query(default=None, alias="processID"),
    datetime_filter: str | None = Query(default=None, alias="datetime"),
    min_duration: int | None = Query(default=None, alias="minDuration", ge=0),
    max_duration: int | None = Query(default=None, alias="maxDuration", ge=0),
):
    payload = await _gcjobs_jobs(request)
    if hasattr(payload, "status_code"):
        return payload

    type_filter = _csv_values(type_values)
    if type_filter and PROCESS_JOB_TYPE not in type_filter:
        mapped: list[dict[str, Any]] = []
    else:
        mapped = payload
    try:
        mapped = _filter_jobs(
            mapped,
            type_values=type_filter,
            process_ids=_csv_values(process_id),
            statuses=_csv_values(status),
            datetime_filter=datetime_filter,
            min_duration=min_duration,
            max_duration=max_duration,
        )
    except ValueError as err:
        return problem_response(
            status_code=400,
            title="Invalid datetime parameter",
            detail=str(err),
        )
    capped = mapped[: max(1, min(limit, 10000))]
    return {
        "jobs": capped,
        "links": [
            {
                "href": str(request.url),
                "rel": "self",
                "type": "application/json",
                "title": "This document",
            }
        ],
    }


@router.get("/jobs/{job_id}")
async def job(request: Request, job_id: str):
    return await proxy_request(
        client=request.app.state.http_client,
        request=request,
        upstream_url=f"{_settings(request).gcjobs_url}/jobs/{job_id}",
        settings=_settings(request),
        catalog=_catalog(request),
        max_upload_bytes=_settings(request).max_upload_bytes,
    )


@router.get("/jobs/{job_id}/results")
async def job_results(request: Request, job_id: str):
    return await proxy_request(
        client=request.app.state.http_client,
        request=request,
        upstream_url=f"{_settings(request).gcjobs_url}/jobs/{job_id}/results",
        settings=_settings(request),
        catalog=_catalog(request),
        max_upload_bytes=_settings(request).max_upload_bytes,
    )
