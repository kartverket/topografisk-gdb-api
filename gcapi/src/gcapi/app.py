from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from gcapi import __version__
from gcapi.config import SERVICE_NAME, Settings
from gcapi.transport import build_runtime_client, proxy_request

PROXY_METHODS = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]
GCJOBS_PROXY_PATH_RE = re.compile(
    r"^datasets/[^/]+/ogc_api/(?:processes/import|jobs)(?:/.*)?$"
)


def create_app(
    *,
    settings: Settings | None = None,
    client: httpx2.AsyncClient | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resolved_settings = settings or Settings.from_env()
        application.state.settings = resolved_settings
        if client is not None:
            application.state.http_client = client
            yield
            return

        async with build_runtime_client(resolved_settings) as runtime_client:
            application.state.http_client = runtime_client
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

    def _upstream_base_url(proxy_path: str) -> str:
        gcjobs_url = application.state.settings.gcjobs_url
        if gcjobs_url and GCJOBS_PROXY_PATH_RE.match(proxy_path.lstrip("/")):
            return gcjobs_url.rstrip("/")
        return application.state.settings.geocomponents_url.rstrip("/")

    def _upstream_url(proxy_path: str) -> str:
        base_url = _upstream_base_url(proxy_path)
        if not proxy_path:
            return base_url
        return f"{base_url}/{proxy_path.lstrip('/')}"

    async def _proxy(request: Request, proxy_path: str):
        return await proxy_request(
            client=application.state.http_client,
            request=request,
            upstream_url=_upstream_url(proxy_path),
            max_upload_bytes=application.state.settings.max_upload_bytes,
        )

    @application.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": SERVICE_NAME}

    @application.api_route("/", methods=PROXY_METHODS)
    async def root_proxy(request: Request):
        return await _proxy(request, "")

    @application.api_route("/{proxy_path:path}", methods=PROXY_METHODS)
    async def catch_all_proxy(request: Request, proxy_path: str):
        return await _proxy(request, proxy_path)

    return application


app = create_app()
