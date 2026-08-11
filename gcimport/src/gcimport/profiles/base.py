"""Dataset-specific import rules consumed by the generic importer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

EXACT_GEOMETRY_MATCH = 2
COMPATIBLE_GEOMETRY_MATCH = 1


@dataclass(frozen=True)
class ImportProfile:
    """Declarative mapping from JSON-FG features to one geocomponents dataset."""

    name: str
    title: str
    default_api_url: str
    target_crs: str
    geometry_type: str
    collections: Mapping[str, str | tuple[str, ...]]
    required_fields: Mapping[str, frozenset[str]]
    identity_fields: tuple[str, ...]
    geometry_types: Mapping[str, str] | None = None
    merge_duplicate_multilinestrings: bool = False

    def __post_init__(self) -> None:
        normalized_required_fields = {
            collection.casefold(): fields
            for collection, fields in self.required_fields.items()
        }
        normalized_collections = {
            feature_type.casefold(): (
                tuple(collection.casefold() for collection in target)
                if isinstance(target, tuple)
                else (target.casefold(),)
            )
            for feature_type, target in self.collections.items()
        }
        normalized_geometry_types = {
            collection.casefold(): geometry_type
            for collection, geometry_type in (self.geometry_types or {}).items()
        }
        for collection in normalized_required_fields:
            normalized_geometry_types.setdefault(collection, self.geometry_type)

        object.__setattr__(
            self, "collections", MappingProxyType(normalized_collections)
        )
        object.__setattr__(
            self,
            "required_fields",
            MappingProxyType(normalized_required_fields),
        )
        object.__setattr__(
            self,
            "geometry_types",
            MappingProxyType(normalized_geometry_types),
        )

    def collection_for(
        self, feature_type: str, geometry_type: str | None = None
    ) -> str | None:
        token = feature_type.casefold()
        if token in self.required_fields:
            return token
        return self.collection_for_objtype(feature_type, geometry_type)

    def collection_for_objtype(
        self,
        objtype: str,
        geometry_type: str | None = None,
    ) -> str | None:
        candidates = self.collections.get(objtype.casefold(), ())
        if len(candidates) == 1:
            return candidates[0]
        if geometry_type is None:
            return None

        exact_matches = [
            collection
            for collection in candidates
            if self.geometry_match_kind(geometry_type, collection)
            == EXACT_GEOMETRY_MATCH
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]
        if exact_matches:
            return None

        compatible_matches = [
            collection
            for collection in candidates
            if self.geometry_match_kind(geometry_type, collection)
            == COMPATIBLE_GEOMETRY_MATCH
        ]
        if len(compatible_matches) == 1:
            return compatible_matches[0]
        return None

    def collections_for_objtype(self, objtype: str) -> tuple[str, ...]:
        return self.collections.get(objtype.casefold(), ())

    def geometry_type_for_collection(self, collection: str) -> str:
        return self.geometry_types[collection.casefold()]

    def geometry_match_kind(self, source_geometry_type: str, collection: str) -> int:
        target_geometry_type = self.geometry_type_for_collection(collection)
        if source_geometry_type == target_geometry_type:
            return EXACT_GEOMETRY_MATCH
        if (
            source_geometry_type == "LineString"
            and target_geometry_type == "MultiLineString"
        ):
            return COMPATIBLE_GEOMETRY_MATCH
        if (
            source_geometry_type == "MultiLineString"
            and target_geometry_type == "MultiPolygon"
        ):
            return COMPATIBLE_GEOMETRY_MATCH
        return 0

    @property
    def supported_feature_types(self) -> str:
        return " or ".join(sorted(set(self.collections) | set(self.required_fields)))

    @property
    def supported_objtypes(self) -> str:
        return " or ".join(sorted(self.collections))
