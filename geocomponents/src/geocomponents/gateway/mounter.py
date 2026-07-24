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

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from geocomponents.api.base import DatasetApiProvider
from geocomponents.descriptions.models import ResolvedDataset
from geocomponents.gateway.index import DatasetMount, dataset_index


def mount_path(dataset_name: str) -> str:
    """The gateway's routing convention (owned here, not by the API adapter)."""
    return f"/datasets/{dataset_name}/ogc_api"


def build_gateway(
    datasets: list[ResolvedDataset],
    provider: DatasetApiProvider,
    base_url: str,
) -> FastAPI:
    base_url = base_url.rstrip("/")
    app = FastAPI(title="geocomponents gateway")

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
