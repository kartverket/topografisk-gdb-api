from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gcapi import __version__
from gcapi.catalog import CatalogSnapshot
from gcapi.config import SERVICE_NAME, Settings
from gcapi.discovery import discover_catalog
from gcapi.features import router as features_router
from gcapi.jobs import router as jobs_router
from gcapi.openapi_doc import build_openapi
from gcapi.processes import router as processes_router
from gcapi.rewrite import landing_links
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

    @application.get("/")
    def root() -> dict[str, object]:
        return {
            "title": "gcapi",
            "description": "Canonical OGC API facade for geocomponents features, processes, and import jobs.",
            "links": landing_links(application.state.settings),
        }

    @application.get("/healthz")
    def healthz():
        if application.state.catalog is None:
            return JSONResponse(
                {"status": "unavailable", "service": SERVICE_NAME}, status_code=503
            )
        return {"status": "ok", "service": SERVICE_NAME}

    @application.get("/conformance")
    def conformance() -> dict[str, object]:
        public_feature_conformance = {
            uri
            for uri in application.state.catalog.feature_conformance
            if uri in PUBLIC_FEATURE_CONFORMANCE_CLASSES
        }
        merged = sorted(public_feature_conformance | set(PROCESS_CONFORMANCE_CLASSES))
        return {"conformsTo": merged}

    @application.get("/openapi")
    def openapi_document() -> dict:
        return build_openapi(application.state.settings, application.state.catalog)

    application.include_router(features_router)
    application.include_router(processes_router)
    application.include_router(jobs_router)
    return application


app = create_app()
