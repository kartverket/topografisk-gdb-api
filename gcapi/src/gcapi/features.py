from __future__ import annotations

from copy import deepcopy

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from gcapi.catalog import CatalogSnapshot, CollectionRoute
from gcapi.config import Settings
from gcapi.problems import problem_response
from gcapi.rewrite import public_url, rewrite_document
from gcapi.transport import proxy_request

router = APIRouter(tags=["features"])


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _catalog(request: Request) -> CatalogSnapshot:
    return request.app.state.catalog


def _collection_route(request: Request, collection_id: str) -> CollectionRoute | None:
    return _catalog(request).collections.get(collection_id)


def _canonical_collection_document(
    route: CollectionRoute,
    *,
    request: Request,
) -> dict:
    payload = deepcopy(route.metadata)
    payload["id"] = route.public_id
    return rewrite_document(
        payload,
        settings=_settings(request),
        catalog=_catalog(request),
        upstream_base_url=route.upstream_base_url,
    )


@router.get("/collections")
def collections(request: Request) -> dict:
    settings = _settings(request)
    catalog = _catalog(request)
    collection_payloads = [
        _canonical_collection_document(route, request=request)
        for route in catalog.collections.values()
    ]
    return {
        "collections": collection_payloads,
        "links": [
            {
                "href": public_url(settings, "/collections"),
                "rel": "self",
                "type": "application/json",
                "title": "This document",
            },
            {
                "href": public_url(settings, "/"),
                "rel": "root",
                "type": "application/json",
                "title": "API landing page",
            },
        ],
    }


@router.get("/collections/{collection_id}")
def collection(request: Request, collection_id: str):
    route = _collection_route(request, collection_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Collection not found",
            detail=f"Unknown collection '{collection_id}'",
        )
    return _canonical_collection_document(route, request=request)


@router.get("/collections/{collection_id}/schema")
def collection_schema(request: Request, collection_id: str):
    route = _collection_route(request, collection_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Collection not found",
            detail=f"Unknown collection '{collection_id}'",
        )
    return rewrite_document(
        route.schema,
        settings=_settings(request),
        catalog=_catalog(request),
        upstream_base_url=route.upstream_base_url,
    )


@router.api_route(
    "/collections/{collection_id}/items",
    methods=["GET", "HEAD", "OPTIONS", "POST"],
)
async def collection_items(request: Request, collection_id: str):
    route = _collection_route(request, collection_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Collection not found",
            detail=f"Unknown collection '{collection_id}'",
        )
    return await proxy_request(
        client=request.app.state.http_client,
        request=request,
        upstream_url=(f"{route.upstream_base_url}/collections/{route.local_id}/items"),
        settings=_settings(request),
        catalog=_catalog(request),
        max_upload_bytes=_settings(request).max_upload_bytes,
    )


@router.post("/collections/{collection_id}/items:upsert")
async def collection_items_upsert(request: Request, collection_id: str):
    route = _collection_route(request, collection_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Collection not found",
            detail=f"Unknown collection '{collection_id}'",
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
    )


@router.api_route(
    "/collections/{collection_id}/items/{feature_id}",
    methods=["GET", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def collection_item(request: Request, collection_id: str, feature_id: str):
    route = _collection_route(request, collection_id)
    if route is None:
        return problem_response(
            status_code=404,
            title="Collection not found",
            detail=f"Unknown collection '{collection_id}'",
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
    )
