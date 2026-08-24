from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DatasetRoute:
    dataset_id: str
    title: str | None
    description: str | None
    upstream_base_url: str
    conformance: tuple[str, ...]


@dataclass(frozen=True)
class CollectionRoute:
    dataset_id: str
    local_id: str
    upstream_base_url: str
    summary: dict[str, Any]
    metadata: dict[str, Any]
    schema: dict[str, Any]
    items_methods: frozenset[str]
    item_methods: frozenset[str]
    supports_upsert: bool = False

    @property
    def public_id(self) -> str:
        return f"{self.dataset_id}.{self.local_id}"


@dataclass(frozen=True)
class ProcessRoute:
    dataset_id: str
    local_id: str
    upstream_base_url: str
    summary: dict[str, Any]
    description: dict[str, Any]

    @property
    def public_id(self) -> str:
        return f"{self.dataset_id}.{self.local_id}"


@dataclass(frozen=True)
class CatalogSnapshot:
    datasets: dict[str, DatasetRoute] = field(default_factory=dict)
    collections: dict[str, CollectionRoute] = field(default_factory=dict)
    processes: dict[str, ProcessRoute] = field(default_factory=dict)
    feature_conformance: tuple[str, ...] = ()
