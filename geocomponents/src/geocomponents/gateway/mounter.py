"""The gateway / mounter component.

Turns a *list* of dataset descriptions into one composite service: it owns the
base URL and the mount-path convention (``/datasets/<name>/ogc_api``), asks the
injected :class:`DatasetApiProvider` to build each dataset's app (passing the
computed public URL), mounts them on a parent FastAPI app, and serves the
top-level dataset index.

It depends only on the ``DatasetApiProvider`` protocol — never on pygeoapi. Swap
the API framework by injecting a different provider; this file is unchanged.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from geocomponents.api.base import DatasetApiProvider
from geocomponents.descriptions.models import ResolvedDataset
from geocomponents.events import OutboxRelay
from geocomponents.gateway.index import DatasetMount, dataset_index


def mount_path(dataset_name: str) -> str:
    """The gateway's routing convention (owned here, not by the API adapter)."""
    return f"/datasets/{dataset_name}/ogc_api"


def build_gateway(
    datasets: list[ResolvedDataset],
    provider: DatasetApiProvider,
    base_url: str,
    event_relay: OutboxRelay | None = None,
) -> FastAPI:
    """Compose one FastAPI service that mounts every dataset's OGC API app on
    the endpoint ``/datasets/<dataset_name>/ogc_api``.
    """
    base_url = base_url.rstrip("/")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if event_relay is None:
            yield
            return

        relay_task = asyncio.create_task(event_relay.run())
        try:
            yield
        finally:
            relay_task.cancel()
            with suppress(asyncio.CancelledError):
                await relay_task
            await event_relay.aclose()

    app = FastAPI(title="geocomponents gateway", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    mounts: list[DatasetMount] = []
    for dataset in datasets:
        path = mount_path(dataset.name)
        public_url = f"{base_url}{path}"
        sub_app = provider.build_app(dataset, public_url)
        app.mount(path, sub_app)
        mounts.append(DatasetMount(dataset, path, public_url))

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/datasets")
    def list_datasets():
        return dataset_index(mounts)

    @app.get("/")
    def root():
        return RedirectResponse(url="/datasets")

    return app
