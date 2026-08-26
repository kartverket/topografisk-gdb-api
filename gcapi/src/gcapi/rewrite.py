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


def dataset_api_path(dataset_id: str, suffix: str = "") -> str:
    base = f"/datasets/{dataset_id}/ogc_api"
    if not suffix:
        return base
    return f"{base}{suffix if suffix.startswith('/') else f'/{suffix}'}"


def landing_links(settings: Settings, dataset_id: str) -> list[dict[str, str]]:
    return [
        link(
            href=public_url(settings, dataset_api_path(dataset_id, "/")),
            rel="self",
            title="This document",
            media_type="application/json",
        ),
        link(
            href=public_url(settings, dataset_api_path(dataset_id, "/openapi")),
            rel="service-desc",
            title="API definition",
            media_type="application/json",
        ),
        link(
            href=public_url(settings, dataset_api_path(dataset_id, "/conformance")),
            rel=CONFORMANCE_REL,
            title="Conformance classes",
            media_type="application/json",
        ),
        link(
            href=public_url(settings, dataset_api_path(dataset_id, "/collections")),
            rel="data",
            title="Collections",
            media_type="application/json",
        ),
        link(
            href=public_url(settings, dataset_api_path(dataset_id, "/processes")),
            rel=PROCESSES_REL,
            title="Processes",
            media_type="application/json",
        ),
        link(
            href=public_url(settings, dataset_api_path(dataset_id, "/jobs")),
            rel=JOB_LIST_REL,
            title="Jobs",
            media_type="application/json",
        ),
    ]


def _rewrite_known_upstream_url(  # noqa: PLR0911
    value: str,
    *,
    settings: Settings,
    catalog: CatalogSnapshot,
    public_api_base_path: str | None = None,
) -> str:
    gcjobs_base = settings.gcjobs_url.rstrip("/")
    if value == f"{gcjobs_base}/jobs" or value.startswith(f"{gcjobs_base}/jobs/"):
        if public_api_base_path is None:
            return value
        suffix = value.removeprefix(f"{gcjobs_base}/jobs")
        return f"{public_url(settings, f'{public_api_base_path}/jobs')}{suffix}"
    if value == f"{gcjobs_base}/processes" or value.startswith(
        f"{gcjobs_base}/processes/"
    ):
        if public_api_base_path is None:
            return value
        suffix = value.removeprefix(f"{gcjobs_base}/processes")
        return f"{public_url(settings, f'{public_api_base_path}/processes')}{suffix}"
    if gcjobs_rewritten := _rewrite_gcjobs_dataset_url(
        value,
        settings=settings,
        catalog=catalog,
    ):
        return gcjobs_rewritten

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
        dataset_base = dataset_api_path(dataset.dataset_id)
        replacements = {
            upstream: public_url(settings, dataset_base),
            f"{upstream}/": public_url(
                settings, dataset_api_path(dataset.dataset_id, "/")
            ),
            f"{upstream}/collections": public_url(
                settings, dataset_api_path(dataset.dataset_id, "/collections")
            ),
            f"{upstream}/conformance": public_url(
                settings, dataset_api_path(dataset.dataset_id, "/conformance")
            ),
            f"{upstream}/openapi": public_url(
                settings, dataset_api_path(dataset.dataset_id, "/openapi")
            ),
            f"{upstream}/processes": public_url(
                settings, dataset_api_path(dataset.dataset_id, "/processes")
            ),
        }
        if value in replacements:
            return replacements[value]
    return value


def _rewrite_gcjobs_dataset_url(
    value: str,
    *,
    settings: Settings,
    catalog: CatalogSnapshot,
) -> str | None:
    gcjobs_base = settings.gcjobs_url.rstrip("/")
    for dataset in catalog.datasets.values():
        gcjobs_dataset_base = f"{gcjobs_base}{dataset_api_path(dataset.dataset_id)}"
        public_dataset_base = public_url(settings, dataset_api_path(dataset.dataset_id))
        for resource_name in ("jobs", "processes"):
            upstream_resource = f"{gcjobs_dataset_base}/{resource_name}"
            if value == upstream_resource or value.startswith(f"{upstream_resource}/"):
                suffix = value.removeprefix(upstream_resource)
                return f"{public_dataset_base}/{resource_name}{suffix}"
    return None


def _rewrite_collection_url(
    value: str,
    route: CollectionRoute,
    settings: Settings,
) -> str | None:
    upstream_prefix = f"{route.upstream_base_url}/collections/{route.local_id}"
    if value == upstream_prefix or value.startswith(f"{upstream_prefix}/"):
        suffix = value.removeprefix(upstream_prefix)
        return f"{public_url(settings, dataset_api_path(route.dataset_id, f'/collections/{route.local_id}'))}{suffix}"
    return None


def _rewrite_process_url(
    value: str,
    route: ProcessRoute,
    settings: Settings,
) -> str | None:
    upstream_prefix = f"{route.upstream_base_url}/processes/{route.local_id}"
    if value == upstream_prefix or value.startswith(f"{upstream_prefix}/"):
        suffix = value.removeprefix(upstream_prefix)
        return f"{public_url(settings, dataset_api_path(route.dataset_id, f'/processes/{route.local_id}'))}{suffix}"
    return None


def rewrite_href(
    value: str,
    *,
    settings: Settings,
    catalog: CatalogSnapshot,
    upstream_base_url: str | None = None,
    public_api_base_path: str | None = None,
) -> str:
    normalized = value.strip()
    if normalized.startswith("/"):
        if upstream_base_url is not None:
            normalized = urljoin(f"{upstream_base_url}/", normalized)
        else:
            normalized = urljoin(f"{settings.geocomponents_url}/", normalized)
    return _rewrite_known_upstream_url(
        normalized,
        settings=settings,
        catalog=catalog,
        public_api_base_path=public_api_base_path,
    )


def rewrite_document(
    value: Any,
    *,
    settings: Settings,
    catalog: CatalogSnapshot,
    upstream_base_url: str | None = None,
    public_api_base_path: str | None = None,
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
                    public_api_base_path=public_api_base_path,
                )
                continue
            rewritten[key] = rewrite_document(
                item,
                settings=settings,
                catalog=catalog,
                upstream_base_url=upstream_base_url,
                public_api_base_path=public_api_base_path,
            )
        return rewritten
    if isinstance(value, list):
        return [
            rewrite_document(
                item,
                settings=settings,
                catalog=catalog,
                upstream_base_url=upstream_base_url,
                public_api_base_path=public_api_base_path,
            )
            for item in value
        ]
    return value
