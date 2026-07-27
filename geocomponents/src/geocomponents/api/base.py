"""The API seam.

``DatasetApiProvider`` is the abstraction the gateway depends on: *given one
resolved dataset and the public URL it will be reachable at, return a mountable
ASGI app*. pygeoapi is one implementation (``pygeoapi_provider.py``); swapping
the API framework means writing another implementation here — the gateway,
schema and descriptions are untouched.

Note the provider is told its ``public_url`` but **not** where/how it is mounted:
the mount-path convention belongs to the gateway, not the API adapter. The
provider only needs the URL so the OGC hypermedia links it generates are correct.
"""

from __future__ import annotations

from typing import Protocol

from starlette.types import ASGIApp

from geocomponents.descriptions.models import ResolvedDataset


class DatasetApiProvider(Protocol):
    def build_app(self, dataset: ResolvedDataset, public_url: str) -> ASGIApp:
        """Build the per-dataset OGC API app, reachable at ``public_url``."""
        ...
