from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from gcapi.catalog import CatalogSnapshot, CollectionRoute, ProcessRoute
from gcapi.config import Settings
from gcapi.ogc import link

CONFORMANCE_REL = "http://www.opengis.net/def/rel/ogc/1.0/conformance"
PROCESSES_REL = "http://www.opengis.net/def/rel/ogc/1.0/processes"
JOB_LIST_REL = "http://www.opengis.net/def/rel/ogc/1.0/job-list"
RESULTS_REL = "http://www.opengis.net/def/rel/ogc/1.0/results"
EXECUTE_REL = "http://www.opengis.net/def/rel/ogc/1.0/execute"


def public_url(settings: Settings, path: str) -> str:
    base = settings.public_url.rstrip("/")
    suffix = path if path.startswith("/") else f"/{path}"
    return f"{base}{suffix}"


def landing_links(settings: Settings) -> list[dict[str, str]]:
    return [
        link(
            href=public_url(settings, "/"),
            rel="self",
            title="This document",
            media_type="application/json",
        ),
        link(
            href=public_url(settings, "/openapi"),
            rel="service-desc",
            title="API definition",
            media_type="application/json",
        ),
        link(
            href=public_url(settings, "/conformance"),
            rel=CONFORMANCE_REL,
            title="Conformance classes",
            media_type="application/json",
        ),
        link(
            href=public_url(settings, "/collections"),
            rel="data",
            title="Collections",
            media_type="application/json",
        ),
        link(
            href=public_url(settings, "/processes"),
            rel=PROCESSES_REL,
            title="Processes",
            media_type="application/json",
        ),
        link(
            href=public_url(settings, "/jobs"),
            rel=JOB_LIST_REL,
            title="Jobs",
            media_type="application/json",
        ),
    ]


def _rewrite_known_upstream_url(
    value: str,
    *,
    settings: Settings,
    catalog: CatalogSnapshot,
) -> str:
    gcjobs_base = settings.gcjobs_url.rstrip("/")
    if value == f"{gcjobs_base}/jobs" or value.startswith(f"{gcjobs_base}/jobs/"):
        suffix = value.removeprefix(f"{gcjobs_base}/jobs")
        return f"{public_url(settings, '/jobs')}{suffix}"
    if value == f"{gcjobs_base}/processes" or value.startswith(
        f"{gcjobs_base}/processes/"
    ):
        suffix = value.removeprefix(f"{gcjobs_base}/processes")
        return f"{public_url(settings, '/processes')}{suffix}"

    for route in catalog.collections.values():
        mapped = _rewrite_collection_url(value, route, settings)
        if mapped is not None:
            return mapped
    for route in catalog.processes.values():
        mapped = _rewrite_process_url(value, route, settings)
        if mapped is not None:
            return mapped
    for dataset in catalog.datasets.values():
        upstream = dataset.upstream_base_url.rstrip("/")
        replacements = {
            upstream: public_url(settings, "/"),
            f"{upstream}/": public_url(settings, "/"),
            f"{upstream}/collections": public_url(settings, "/collections"),
            f"{upstream}/conformance": public_url(settings, "/conformance"),
            f"{upstream}/openapi": public_url(settings, "/openapi"),
            f"{upstream}/processes": public_url(settings, "/processes"),
        }
        if value in replacements:
            return replacements[value]
    return value


def _rewrite_collection_url(
    value: str,
    route: CollectionRoute,
    settings: Settings,
) -> str | None:
    upstream_prefix = f"{route.upstream_base_url}/collections/{route.local_id}"
    if value == upstream_prefix or value.startswith(f"{upstream_prefix}/"):
        suffix = value.removeprefix(upstream_prefix)
        return f"{public_url(settings, f'/collections/{route.public_id}')}{suffix}"
    return None


def _rewrite_process_url(
    value: str,
    route: ProcessRoute,
    settings: Settings,
) -> str | None:
    upstream_prefix = f"{route.upstream_base_url}/processes/{route.local_id}"
    if value == upstream_prefix or value.startswith(f"{upstream_prefix}/"):
        suffix = value.removeprefix(upstream_prefix)
        return f"{public_url(settings, f'/processes/{route.public_id}')}{suffix}"
    return None


def rewrite_href(
    value: str,
    *,
    settings: Settings,
    catalog: CatalogSnapshot,
    upstream_base_url: str | None = None,
) -> str:
    normalized = value.strip()
    if normalized.startswith("/"):
        if upstream_base_url is not None:
            normalized = urljoin(f"{upstream_base_url}/", normalized)
        else:
            normalized = urljoin(f"{settings.geocomponents_url}/", normalized)
    return _rewrite_known_upstream_url(normalized, settings=settings, catalog=catalog)


def rewrite_document(
    value: Any,
    *,
    settings: Settings,
    catalog: CatalogSnapshot,
    upstream_base_url: str | None = None,
) -> Any:
    if isinstance(value, dict):
        rewritten: dict[str, Any] = {}
        for key, item in value.items():
            if key == "href" and isinstance(item, str):
                rewritten[key] = rewrite_href(
                    item,
                    settings=settings,
                    catalog=catalog,
                    upstream_base_url=upstream_base_url,
                )
                continue
            rewritten[key] = rewrite_document(
                item,
                settings=settings,
                catalog=catalog,
                upstream_base_url=upstream_base_url,
            )
        return rewritten
    if isinstance(value, list):
        return [
            rewrite_document(
                item,
                settings=settings,
                catalog=catalog,
                upstream_base_url=upstream_base_url,
            )
            for item in value
        ]
    return value
