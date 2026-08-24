from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx2

from gcapi.catalog import CatalogSnapshot, CollectionRoute, DatasetRoute, ProcessRoute
from gcapi.config import Settings

ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class DiscoveryError(RuntimeError):
    pass


def _normalize_base_url(url: str) -> str:
    return url.rstrip("/")


def _public_id(dataset_id: str, local_id: str) -> str:
    return f"{dataset_id}.{local_id}"


def _require_mapping(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DiscoveryError(
            f"Malformed upstream payload for {context}: expected object"
        )
    return value


def _require_list(value: Any, *, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise DiscoveryError(
            f"Malformed upstream payload for {context}: expected array"
        )
    return value


def _validate_id(raw_value: Any, *, kind: str, dataset_id: str | None = None) -> str:
    if not isinstance(raw_value, str) or not raw_value:
        raise DiscoveryError(f"Malformed upstream {kind}: missing id")
    if not ID_PATTERN.fullmatch(raw_value):
        if dataset_id is None:
            raise DiscoveryError(f"Malformed upstream {kind} id '{raw_value}'")
        raise DiscoveryError(
            f"Malformed upstream {kind} id '{raw_value}' for dataset '{dataset_id}'"
        )
    return raw_value


def _allow_methods(headers: httpx2.Headers) -> frozenset[str]:
    raw_allow = headers.get("Allow", "")
    methods = {
        method.strip().upper() for method in raw_allow.split(",") if method.strip()
    }
    return frozenset(methods)


async def _read_json(
    client: httpx2.AsyncClient, url: str, *, context: str
) -> dict[str, Any]:
    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx2.TimeoutException as err:
        raise DiscoveryError(f"Timed out reading {context} from {url}") from err
    except httpx2.HTTPError as err:
        raise DiscoveryError(f"Could not read {context} from {url}: {err}") from err

    try:
        payload = response.json()
    except ValueError as err:
        raise DiscoveryError(f"Malformed JSON for {context} from {url}") from err
    return _require_mapping(payload, context=context)


async def _read_options(
    client: httpx2.AsyncClient,
    url: str,
    *,
    context: str,
) -> frozenset[str]:
    try:
        response = await client.options(url)
        response.raise_for_status()
    except httpx2.TimeoutException as err:
        raise DiscoveryError(f"Timed out reading {context} from {url}") from err
    except httpx2.HTTPError as err:
        raise DiscoveryError(f"Could not read {context} from {url}: {err}") from err
    return _allow_methods(response.headers)


def _dataset_base_url(
    settings: Settings, dataset_summary: dict[str, Any], dataset_id: str
) -> str:
    links = dataset_summary.get("links")
    if isinstance(links, list):
        for link in links:
            if isinstance(link, dict) and link.get("rel") == "service-desc":
                href = link.get("href")
                if isinstance(href, str) and href.strip():
                    advertised = href.strip()
                    if advertised.startswith("/"):
                        return _normalize_base_url(
                            urljoin(f"{settings.geocomponents_url}/", advertised)
                        )

                    parts = urlsplit(advertised)
                    if parts.scheme and parts.netloc:
                        upstream_parts = urlsplit(settings.geocomponents_url)
                        rebased = urlunsplit(
                            (
                                upstream_parts.scheme,
                                upstream_parts.netloc,
                                parts.path,
                                parts.query,
                                parts.fragment,
                            )
                        )
                        return _normalize_base_url(rebased)
                    return _normalize_base_url(
                        urljoin(f"{settings.geocomponents_url}/", advertised)
                    )
    return f"{settings.geocomponents_url}/datasets/{dataset_id}/ogc_api"


def _merge_conformance(values: Iterable[Iterable[str]]) -> tuple[str, ...]:
    merged = {value for group in values for value in group}
    return tuple(sorted(merged))


async def discover_catalog(
    client: httpx2.AsyncClient,
    settings: Settings,
) -> CatalogSnapshot:
    dataset_index = await _read_json(
        client,
        f"{settings.geocomponents_url}/datasets",
        context="dataset index",
    )
    dataset_summaries = _require_list(
        dataset_index.get("datasets"), context="dataset index"
    )

    datasets: dict[str, DatasetRoute] = {}
    collections: dict[str, CollectionRoute] = {}
    processes: dict[str, ProcessRoute] = {}
    feature_conformance_groups: list[tuple[str, ...]] = []

    dataset_ids: list[str] = []
    normalized_dataset_summaries: list[dict[str, Any]] = []
    for dataset_summary in dataset_summaries:
        summary = _require_mapping(dataset_summary, context="dataset summary")
        dataset_id = _validate_id(summary.get("id"), kind="dataset")
        dataset_ids.append(dataset_id)
        normalized_dataset_summaries.append(summary)

    seen_dataset_ids: set[str] = set()
    for dataset_id in dataset_ids:
        if dataset_id in seen_dataset_ids:
            raise DiscoveryError(f"Duplicate dataset id '{dataset_id}'")
        seen_dataset_ids.add(dataset_id)

    for summary, dataset_id in zip(
        normalized_dataset_summaries, dataset_ids, strict=True
    ):
        upstream_base_url = _dataset_base_url(settings, summary, dataset_id)
        collections_doc = await _read_json(
            client,
            f"{upstream_base_url}/collections?f=json",
            context=f"collections list for {dataset_id}",
        )
        conformance_doc = await _read_json(
            client,
            f"{upstream_base_url}/conformance?f=json",
            context=f"conformance for {dataset_id}",
        )
        processes_doc = await _read_json(
            client,
            f"{upstream_base_url}/processes?f=json",
            context=f"process list for {dataset_id}",
        )
        openapi_doc = await _read_json(
            client,
            f"{upstream_base_url}/openapi?f=json",
            context=f"openapi for {dataset_id}",
        )

        conforms_to = tuple(
            value
            for value in _require_list(
                conformance_doc.get("conformsTo"),
                context=f"conformance for {dataset_id}",
            )
            if isinstance(value, str)
        )
        feature_conformance_groups.append(conforms_to)
        datasets[dataset_id] = DatasetRoute(
            dataset_id=dataset_id,
            title=summary.get("title")
            if isinstance(summary.get("title"), str)
            else None,
            description=(
                summary.get("description")
                if isinstance(summary.get("description"), str)
                else None
            ),
            upstream_base_url=upstream_base_url,
            conformance=conforms_to,
        )

        openapi_paths = _require_mapping(
            openapi_doc.get("paths"),
            context=f"openapi paths for {dataset_id}",
        )

        for collection_summary in _require_list(
            collections_doc.get("collections"),
            context=f"collections list for {dataset_id}",
        ):
            summary_payload = _require_mapping(
                collection_summary,
                context=f"collection summary for {dataset_id}",
            )
            local_id = _validate_id(
                summary_payload.get("id"),
                kind="collection",
                dataset_id=dataset_id,
            )
            public_id = _public_id(dataset_id, local_id)
            if public_id in collections:
                raise DiscoveryError(f"Duplicate canonical collection id '{public_id}'")

            metadata = await _read_json(
                client,
                f"{upstream_base_url}/collections/{local_id}?f=json",
                context=f"collection {public_id}",
            )
            schema = await _read_json(
                client,
                f"{upstream_base_url}/collections/{local_id}/schema",
                context=f"collection schema {public_id}",
            )
            items_methods = await _read_options(
                client,
                f"{upstream_base_url}/collections/{local_id}/items",
                context=f"collection items methods {public_id}",
            )
            item_methods = await _read_options(
                client,
                f"{upstream_base_url}/collections/{local_id}/items/__gcapi_probe__",
                context=f"collection item methods {public_id}",
            )
            supports_upsert = f"/collections/{local_id}/items:upsert" in openapi_paths
            collections[public_id] = CollectionRoute(
                dataset_id=dataset_id,
                local_id=local_id,
                upstream_base_url=upstream_base_url,
                summary=summary_payload,
                metadata=metadata,
                schema=schema,
                items_methods=items_methods,
                item_methods=item_methods,
                supports_upsert=supports_upsert,
            )

        for process_summary in _require_list(
            processes_doc.get("processes"),
            context=f"process list for {dataset_id}",
        ):
            summary_payload = _require_mapping(
                process_summary,
                context=f"process summary for {dataset_id}",
            )
            local_id = _validate_id(
                summary_payload.get("id"),
                kind="process",
                dataset_id=dataset_id,
            )
            public_id = _public_id(dataset_id, local_id)
            if public_id in processes:
                raise DiscoveryError(f"Duplicate canonical process id '{public_id}'")
            description = await _read_json(
                client,
                f"{upstream_base_url}/processes/{local_id}?f=json",
                context=f"process {public_id}",
            )
            processes[public_id] = ProcessRoute(
                dataset_id=dataset_id,
                local_id=local_id,
                upstream_base_url=upstream_base_url,
                summary=summary_payload,
                description=description,
            )

    return CatalogSnapshot(
        datasets=datasets,
        collections=collections,
        processes=processes,
        feature_conformance=_merge_conformance(feature_conformance_groups),
    )
