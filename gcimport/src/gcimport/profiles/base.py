"""Dataset-specific import rules consumed by the generic importer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class ImportProfile:
    """Declarative mapping from JSON-FG features to one geocomponents dataset."""

    name: str
    title: str
    default_api_url: str
    target_crs: str
    geometry_type: str
    collections: Mapping[str, str]
    required_fields: Mapping[str, frozenset[str]]
    identity_fields: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "collections", MappingProxyType(dict(self.collections))
        )
        object.__setattr__(
            self,
            "required_fields",
            MappingProxyType(dict(self.required_fields)),
        )

    def collection_for(self, feature_type: str) -> str | None:
        return self.collections.get(feature_type.casefold())

    @property
    def supported_feature_types(self) -> str:
        return " or ".join(sorted(self.collections))
