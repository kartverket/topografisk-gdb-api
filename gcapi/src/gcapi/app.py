from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from gcapi import __version__
from gcapi.catalog import CatalogSnapshot
from gcapi.config import SERVICE_NAME, Settings
from gcapi.discovery import discover_catalog
from gcapi.features import router as features_router
from gcapi.jobs import router as jobs_router
from gcapi.openapi_doc import build_openapi
from gcapi.problems import problem_response
from gcapi.processes import router as processes_router
from gcapi.rewrite import dataset_api_path, landing_links, public_url
from gcapi.transport import build_runtime_client

# The facade exposes process-like routes, but its built-in import execution does not yet
# satisfy the canonical OGC API - Processes execute contract. Under-claim conformance
# until the public wire behavior matches the advertised requirements classes.
PROCESS_CONFORMANCE_CLASSES: tuple[str, ...] = ()

# The facade is not a transparent pass-through for every upstream feature capability.
# Only advertise the minimal feature conformance class that the public surface can
# safely restate without matching every upstream wire-level detail.
PUBLIC_FEATURE_CONFORMANCE_CLASSES = (
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
)


def create_app(
    *,
    settings: Settings | None = None,
    client: httpx2.AsyncClient | None = None,
    catalog: CatalogSnapshot | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resolved_settings = settings or Settings.from_env()
        application.state.settings = resolved_settings
        application.state.catalog = catalog
        if client is not None:
            application.state.http_client = client
            if application.state.catalog is None:
                application.state.catalog = await discover_catalog(
                    client, resolved_settings
                )
            yield
            return

        async with build_runtime_client(resolved_settings) as runtime_client:
            application.state.http_client = runtime_client
            if application.state.catalog is None:
                application.state.catalog = await discover_catalog(
                    runtime_client,
                    resolved_settings,
                )
            yield

    application = FastAPI(
        title=SERVICE_NAME,
        version=__version__,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "Location",
            "Link",
            "ETag",
            "Content-Crs",
            "Preference-Applied",
        ],
    )

    def _dataset_payload(dataset_id: str) -> dict[str, object] | None:
        dataset = application.state.catalog.datasets.get(dataset_id)
        if dataset is None:
            return None
        collections = sorted(
            route.local_id
            for route in application.state.catalog.collections.values()
            if route.dataset_id == dataset_id
        )
        return {
            "id": dataset.dataset_id,
            "title": dataset.title,
            "description": dataset.description,
            "collections": collections,
            "links": [
                {
                    "rel": "service-desc",
                    "type": "application/json",
                    "title": f"OGC API for '{dataset.dataset_id}'",
                    "href": public_url(
                        application.state.settings,
                        dataset_api_path(dataset.dataset_id, "/"),
                    ),
                }
            ],
        }

    @application.get("/")
    def root():
        return RedirectResponse(url="/datasets")

    @application.get("/datasets")
    def datasets() -> dict[str, object]:
        return {
            "title": "gcapi datasets",
            "description": "Each dataset is served as its own OGC API.",
            "datasets": [
                payload
                for dataset_id in sorted(application.state.catalog.datasets)
                if (payload := _dataset_payload(dataset_id)) is not None
            ],
        }

    @application.get("/healthz")
    def healthz():
        if application.state.catalog is None:
            return JSONResponse(
                {"status": "unavailable", "service": SERVICE_NAME}, status_code=503
            )
        return {"status": "ok", "service": SERVICE_NAME}

    @application.get("/datasets/{dataset_id}/ogc_api/")
    def dataset_landing(dataset_id: str):
        dataset = application.state.catalog.datasets.get(dataset_id)
        if dataset is None:
            return problem_response(
                status_code=404,
                title="Dataset not found",
                detail=f"Unknown dataset '{dataset_id}'",
            )
        return {
            "title": dataset.title or dataset.dataset_id,
            "description": dataset.description or "Dataset OGC API facade.",
            "links": landing_links(application.state.settings, dataset_id),
        }

    @application.get("/datasets/{dataset_id}/ogc_api/conformance")
    def conformance(dataset_id: str):
        dataset = application.state.catalog.datasets.get(dataset_id)
        if dataset is None:
            return problem_response(
                status_code=404,
                title="Dataset not found",
                detail=f"Unknown dataset '{dataset_id}'",
            )
        public_feature_conformance = {
            uri
            for uri in dataset.conformance
            if uri in PUBLIC_FEATURE_CONFORMANCE_CLASSES
        }
        merged = sorted(public_feature_conformance | set(PROCESS_CONFORMANCE_CLASSES))
        return {"conformsTo": merged}

    @application.get("/datasets/{dataset_id}/ogc_api/openapi")
    def openapi_document(dataset_id: str):
        if dataset_id not in application.state.catalog.datasets:
            return problem_response(
                status_code=404,
                title="Dataset not found",
                detail=f"Unknown dataset '{dataset_id}'",
            )
        return build_openapi(
            application.state.settings,
            application.state.catalog,
            dataset_id,
        )

    application.include_router(features_router)
    application.include_router(processes_router)
    application.include_router(jobs_router)
    return application


app = create_app()
