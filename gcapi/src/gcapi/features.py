from __future__ import annotations

from copy import deepcopy

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gcapi.catalog import CatalogSnapshot, CollectionRoute
from gcapi.config import Settings
from gcapi.problems import problem_response
from gcapi.rewrite import dataset_api_path, public_url, rewrite_document
from gcapi.transport import proxy_request

router = APIRouter(tags=["features"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _catalog(request: Request) -> CatalogSnapshot:
    return request.app.state.catalog


def _collection_route(
    request: Request, dataset_id: str, collection_id: str
) -> CollectionRoute | None:
    return _catalog(request).collections.get(f"{dataset_id}.{collection_id}")


def _dataset_exists(request: Request, dataset_id: str) -> bool:
    return dataset_id in _catalog(request).datasets


def _canonical_collection_document(
    route: CollectionRoute,
    *,
    request: Request,
) -> dict:
    payload = deepcopy(route.metadata)
    payload["id"] = route.local_id
    return rewrite_document(
        payload,
        settings=_settings(request),
        catalog=_catalog(request),
        upstream_base_url=route.upstream_base_url,
        public_api_base_path=dataset_api_path(route.dataset_id),
    )


@router.get("/datasets/{dataset_id}/ogc_api/collections")
def collections(request: Request, dataset_id: str):
    if not _dataset_exists(request, dataset_id):
        return problem_response(
            status_code=404,
            title="Dataset not found",
            detail=f"Unknown dataset '{dataset_id}'",
        )
    settings = _settings(request)
    catalog = _catalog(request)
    collection_payloads = [
        _canonical_collection_document(route, request=request)
        for route in catalog.collections.values()
        if route.dataset_id == dataset_id
    ]
    return {
        "collections": collection_payloads,
        "links": [
            {
                "href": public_url(
                    settings, dataset_api_path(dataset_id, "/collections")
                ),
                "rel": "self",
                "type": "application/json",
                "title": "This document",
            },
            {
                "href": public_url(settings, dataset_api_path(dataset_id, "/")),
                "rel": "root",
                "type": "application/json",
                "title": "API landing page",
            },
        ],
    }


@router.get("/datasets/{dataset_id}/ogc_api/collections/{collection_id}")
def collection(request: Request, dataset_id: str, collection_id: str):
    route = _collection_route(request, dataset_id, collection_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Collection not found",
            detail=f"Unknown collection '{collection_id}' for dataset '{dataset_id}'",
        )
    return _canonical_collection_document(route, request=request)


@router.get("/datasets/{dataset_id}/ogc_api/collections/{collection_id}/schema")
def collection_schema(request: Request, dataset_id: str, collection_id: str):
    route = _collection_route(request, dataset_id, collection_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Collection not found",
            detail=f"Unknown collection '{collection_id}' for dataset '{dataset_id}'",
        )
    return rewrite_document(
        route.schema,
        settings=_settings(request),
        catalog=_catalog(request),
        upstream_base_url=route.upstream_base_url,
        public_api_base_path=dataset_api_path(route.dataset_id),
    )


@router.api_route(
    "/datasets/{dataset_id}/ogc_api/collections/{collection_id}/items",
    methods=["GET", "HEAD", "OPTIONS", "POST"],
)
async def collection_items(request: Request, dataset_id: str, collection_id: str):
    route = _collection_route(request, dataset_id, collection_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Collection not found",
            detail=f"Unknown collection '{collection_id}' for dataset '{dataset_id}'",
        )
    return await proxy_request(
        client=request.app.state.http_client,
        request=request,
        upstream_url=(f"{route.upstream_base_url}/collections/{route.local_id}/items"),
        settings=_settings(request),
        catalog=_catalog(request),
        max_upload_bytes=_settings(request).max_upload_bytes,
        public_api_base_path=dataset_api_path(dataset_id),
    )


@router.post("/datasets/{dataset_id}/ogc_api/collections/{collection_id}/items:upsert")
async def collection_items_upsert(
    request: Request, dataset_id: str, collection_id: str
):
    route = _collection_route(request, dataset_id, collection_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Collection not found",
            detail=f"Unknown collection '{collection_id}' for dataset '{dataset_id}'",
        )
    if not route.supports_upsert:
        return JSONResponse(
            {"detail": "items:upsert is not available for this collection"},
            status_code=405,
            headers={"Allow": ", ".join(sorted(route.items_methods))},
        )
    return await proxy_request(
        client=request.app.state.http_client,
        request=request,
        upstream_url=(
            f"{route.upstream_base_url}/collections/{route.local_id}/items:upsert"
        ),
        settings=_settings(request),
        catalog=_catalog(request),
        max_upload_bytes=_settings(request).max_upload_bytes,
        public_api_base_path=dataset_api_path(dataset_id),
    )


@router.api_route(
    "/datasets/{dataset_id}/ogc_api/collections/{collection_id}/items/{feature_id}",
    methods=["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def collection_item(
    request: Request, dataset_id: str, collection_id: str, feature_id: str
):
    route = _collection_route(request, dataset_id, collection_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Collection not found",
            detail=f"Unknown collection '{collection_id}' for dataset '{dataset_id}'",
        )
    return await proxy_request(
        client=request.app.state.http_client,
        request=request,
        upstream_url=(
            f"{route.upstream_base_url}/collections/{route.local_id}/items/{feature_id}"
        ),
        settings=_settings(request),
        catalog=_catalog(request),
        max_upload_bytes=_settings(request).max_upload_bytes,
        public_api_base_path=dataset_api_path(dataset_id),
    )
