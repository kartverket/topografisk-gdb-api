"""Top-level dataset catalog.

The gateway exposes a small index over all mounted datasets, with links into
each one's self-contained OGC API. This is also the natural future home for
cross-cutting concerns (auth, events, dataset lifecycle).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..descriptions.models import ResolvedDataset


@dataclass(frozen=True)
class DatasetMount:
    dataset: ResolvedDataset
    mount_path: str   # e.g. /datasets/cadastre/ogc_api
    public_url: str   # absolute URL to that dataset's OGC API landing page


def dataset_index(mounts: list[DatasetMount]) -> dict:
    return {
        "title": "geocomponents datasets",
        "description": "Each dataset is served as its own OGC API.",
        "datasets": [
            {
                "id": m.dataset.name,
                "title": m.dataset.title,
                "description": m.dataset.description,
                "collections": [c.name for c in m.dataset.collections],
                "links": [
                    {
                        "rel": "service-desc",
                        "type": "application/json",
                        "title": f"OGC API for '{m.dataset.name}'",
                        "href": m.public_url + "/",
                    }
                ],
            }
            for m in mounts
        ],
    }
