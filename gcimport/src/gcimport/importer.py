"""Validation, JSON-FG conversion, and upstream import logic."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from pyproj import CRS, Transformer
from pyproj.exceptions import CRSError, ProjError

from gcimport.profiles.base import ImportProfile

FALLBACK_GEOMETRY_CRS = "EPSG:4326"
MIN_LINESTRING_POSITIONS = 2
MIN_LINEAR_RING_POSITIONS = 4
MIN_POSITION_DIMENSIONS = 2
MAX_POSITION_DIMENSIONS = 3
_DUPLICATE_MERGE_IGNORED_PROPERTIES = frozenset({"OBJECTID", "SHAPE_Length"})


class DocumentValidationError(ValueError):
    """Raised when the uploaded JSON-FG document is invalid."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class UpstreamImportError(RuntimeError):
    """Raised when an individual upstream upsert fails."""

    def __init__(
        self,
        *,
        collection: str,
        feature_id: str,
        reason: str,
    ) -> None:
        super().__init__(reason)
        self.collection = collection
        self.feature_id = feature_id
        self.reason = reason


@dataclass(frozen=True)
class PreparedFeature:
    """A validated GeoJSON feature and its upstream route."""

    collection: str
    feature_id: str
    geojson: dict[str, Any]


def _identity_values(
    properties: dict[str, Any],
    profile: ImportProfile,
) -> tuple[list[str], list[str]]:
    values: list[str] = []
    errors: list[str] = []
    for name in profile.identity_fields:
        value = properties.get(name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"properties.{name} must be a non-empty string")
        else:
            values.append(value.strip())
    return values, errors


def prepare_document(
    document: Any,
    profile: ImportProfile,
) -> list[PreparedFeature]:
    """Validate an entire JSON-FG FeatureCollection before returning any work."""
    if not isinstance(document, dict):
        raise DocumentValidationError(["document must be a JSON object"])
    if document.get("type") != "FeatureCollection":
        raise DocumentValidationError(["type must be 'FeatureCollection'"])

    features = document.get("features")
    if not isinstance(features, list):
        raise DocumentValidationError(["features must be an array"])

    inherited_crs = document.get("coordRefSys")
    errors: list[str] = []
    prepared: list[PreparedFeature] = []
    identity_indexes: dict[tuple[str, ...], int] = {}

    for index, feature in enumerate(features):
        try:
            item = _prepare_feature(feature, inherited_crs, profile)
            identity = tuple(
                str(item.geojson["properties"][name])
                for name in profile.identity_fields
            )
            existing_index = identity_indexes.get(identity)
            if existing_index is None:
                identity_indexes[identity] = len(prepared)
                prepared.append(item)
                continue

            merged = _merge_duplicate_feature(
                prepared[existing_index], item, profile=profile
            )
            if merged is None:
                errors.append(
                    f"features[{index}]: duplicate "
                    f"({', '.join(profile.identity_fields)})"
                )
                continue

            prepared[existing_index] = merged
        except DocumentValidationError as err:
            errors.extend(f"features[{index}]: {message}" for message in err.errors)

    if errors:
        raise DocumentValidationError(errors)
    return prepared


def _merge_duplicate_feature(
    existing: PreparedFeature,
    incoming: PreparedFeature,
    *,
    profile: ImportProfile,
) -> PreparedFeature | None:
    if not profile.merge_duplicate_multilinestrings:
        return None

    existing_properties = existing.geojson.get("properties")
    incoming_properties = incoming.geojson.get("properties")
    existing_geometry = existing.geojson.get("geometry")
    incoming_geometry = incoming.geojson.get("geometry")

    if (
        existing.collection != incoming.collection
        or existing.feature_id != incoming.feature_id
        or not isinstance(existing_properties, dict)
        or not isinstance(incoming_properties, dict)
        or not isinstance(existing_geometry, dict)
        or not isinstance(incoming_geometry, dict)
        or existing_geometry.get("type") != "MultiLineString"
        or incoming_geometry.get("type") != "MultiLineString"
    ):
        return None

    if _comparable_properties(existing_properties) != _comparable_properties(
        incoming_properties
    ):
        return None

    existing_coordinates = existing_geometry.get("coordinates")
    incoming_coordinates = incoming_geometry.get("coordinates")
    if not isinstance(existing_coordinates, list) or not isinstance(
        incoming_coordinates, list
    ):
        return None

    return PreparedFeature(
        collection=existing.collection,
        feature_id=existing.feature_id,
        geojson={
            **existing.geojson,
            "geometry": {
                "type": "MultiLineString",
                "coordinates": [*existing_coordinates, *incoming_coordinates],
            },
        },
    )


def _comparable_properties(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        name: value
        for name, value in properties.items()
        if name not in _DUPLICATE_MERGE_IGNORED_PROPERTIES
    }


def _prepare_feature(
    feature: Any,
    inherited_crs: Any,
    profile: ImportProfile,
) -> PreparedFeature:
    errors: list[str] = []
    if not isinstance(feature, dict):
        raise DocumentValidationError(["feature must be a JSON object"])
    if feature.get("type") != "Feature":
        errors.append("type must be 'Feature'")

    raw_feature_type = feature.get("featureType")
    collection = ""

    properties = feature.get("properties")
    if not isinstance(properties, dict):
        errors.append("properties must be an object")
        properties = {}

    identity_values, identity_errors = _identity_values(properties, profile)
    errors.extend(identity_errors)

    try:
        geometry, source_crs = _select_geometry(feature, inherited_crs)
        geometry_type = geometry.get("type") if isinstance(geometry, dict) else None
        if not isinstance(raw_feature_type, str):
            errors.append("featureType must be a string")
        else:
            collection = profile.collection_for(raw_feature_type, geometry_type) or ""
            if not collection:
                errors.append(f"featureType must be {profile.supported_feature_types}")
        if collection:
            missing = sorted(
                name
                for name in profile.required_fields[collection]
                if name not in properties or properties[name] is None
            )
            if missing:
                errors.append(f"missing required properties: {', '.join(missing)}")
            transformed_geometry = _transform_geometry(
                geometry,
                source_crs,
                profile,
                collection,
            )
        else:
            transformed_geometry = {}
    except DocumentValidationError as err:
        errors.extend(err.errors)
        transformed_geometry = {}

    if errors:
        raise DocumentValidationError(errors)

    feature_id = identity_values[0]
    return PreparedFeature(
        collection=collection,
        feature_id=feature_id,
        geojson={
            "type": "Feature",
            "id": feature_id,
            "geometry": transformed_geometry,
            "properties": properties,
        },
    )


def _select_geometry(
    feature: dict[str, Any],
    inherited_crs: Any,
) -> tuple[dict[str, Any], str]:
    place = feature.get("place")
    if place is not None:
        if not isinstance(place, dict):
            raise DocumentValidationError(["place must be a geometry object"])
        source_crs = place.get(
            "coordRefSys",
            feature.get("coordRefSys", inherited_crs),
        )
        if source_crs is None:
            raise DocumentValidationError(
                ["place requires coordRefSys on place, feature, or collection"]
            )
        if not isinstance(source_crs, str) or not source_crs.strip():
            raise DocumentValidationError(["coordRefSys must be a non-empty string"])
        return place, source_crs

    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise DocumentValidationError(
            ["feature requires a JSON-FG place or GeoJSON geometry"]
        )
    return geometry, FALLBACK_GEOMETRY_CRS


def _transform_geometry(
    geometry: dict[str, Any],
    source_crs: str,
    profile: ImportProfile,
    collection: str,
) -> dict[str, Any]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    target_geometry_type = profile.geometry_type_for_collection(collection)

    if geometry_type == "LineString" and target_geometry_type == "MultiLineString":
        geometry_type = "MultiLineString"
        coordinates = [coordinates]

    if geometry_type != target_geometry_type:
        raise DocumentValidationError([f"geometry must be a {target_geometry_type}"])

    try:
        transformer = Transformer.from_crs(
            CRS.from_user_input(source_crs),
            CRS.from_user_input(profile.target_crs),
            always_xy=True,
        )
        transformed = _transform_coordinates(
            geometry_type,
            coordinates,
            transformer,
        )
    except (CRSError, ProjError) as err:
        raise DocumentValidationError(
            [f"cannot transform coordRefSys '{source_crs}' to {profile.target_crs}"]
        ) from err

    if any(
        not math.isfinite(value)
        for position in _iter_positions(transformed)
        for value in position
    ):
        raise DocumentValidationError(
            [f"coordinate transform from '{source_crs}' produced invalid values"]
        )
    return {"type": geometry_type, "coordinates": transformed}


def _transform_coordinates(
    geometry_type: Any,
    coordinates: Any,
    transformer: Transformer,
) -> list[Any]:
    if geometry_type == "LineString":
        return _transform_linestring_coordinates(coordinates, transformer)
    if geometry_type == "MultiLineString":
        return _transform_multilinestring_coordinates(coordinates, transformer)
    if geometry_type == "Polygon":
        return _transform_polygon_coordinates(coordinates, transformer)
    if geometry_type == "MultiPolygon":
        return _transform_multipolygon_coordinates(coordinates, transformer)
    raise DocumentValidationError([f"geometry type {geometry_type} is not implemented"])


def _transform_linestring_coordinates(
    coordinates: Any,
    transformer: Transformer,
) -> list[list[float]]:
    if not isinstance(coordinates, list) or len(coordinates) < MIN_LINESTRING_POSITIONS:
        raise DocumentValidationError(
            ["LineString coordinates must contain at least two positions"]
        )
    return [
        _transform_position(
            position,
            transformer,
            geometry_type="LineString",
            path=f"position {position_index}",
        )
        for position_index, position in enumerate(coordinates)
    ]


def _transform_polygon_coordinates(
    coordinates: Any,
    transformer: Transformer,
) -> list[list[list[float]]]:
    if not isinstance(coordinates, list) or not coordinates:
        raise DocumentValidationError(
            ["Polygon coordinates must contain at least one ring"]
        )
    return [
        _transform_ring(
            ring,
            transformer,
            geometry_type="Polygon",
            path=f"ring {ring_index}",
        )
        for ring_index, ring in enumerate(coordinates)
    ]


def _transform_multilinestring_coordinates(
    coordinates: Any,
    transformer: Transformer,
) -> list[list[list[float]]]:
    if not isinstance(coordinates, list) or not coordinates:
        raise DocumentValidationError(
            ["MultiLineString coordinates must contain at least one line"]
        )
    transformed: list[list[list[float]]] = []
    for line_index, line in enumerate(coordinates):
        if not isinstance(line, list) or len(line) < MIN_LINESTRING_POSITIONS:
            raise DocumentValidationError(
                [
                    "MultiLineString line "
                    f"{line_index} must contain at least two positions"
                ]
            )
        transformed.append(
            [
                _transform_position(
                    position,
                    transformer,
                    geometry_type="MultiLineString",
                    path=f"line {line_index} position {position_index}",
                )
                for position_index, position in enumerate(line)
            ]
        )
    return transformed


def _transform_multipolygon_coordinates(
    coordinates: Any,
    transformer: Transformer,
) -> list[list[list[list[float]]]]:
    if not isinstance(coordinates, list) or not coordinates:
        raise DocumentValidationError(
            ["MultiPolygon coordinates must contain at least one polygon"]
        )

    transformed: list[list[list[list[float]]]] = []
    for polygon_index, polygon in enumerate(coordinates):
        if not isinstance(polygon, list) or not polygon:
            raise DocumentValidationError(
                [
                    "MultiPolygon polygon "
                    f"{polygon_index} must contain at least one ring"
                ]
            )
        transformed.append(
            [
                _transform_ring(
                    ring,
                    transformer,
                    geometry_type="MultiPolygon",
                    path=f"polygon {polygon_index} ring {ring_index}",
                )
                for ring_index, ring in enumerate(polygon)
            ]
        )
    return transformed


def _transform_ring(
    ring: Any,
    transformer: Transformer,
    *,
    geometry_type: str,
    path: str,
) -> list[list[float]]:
    if not isinstance(ring, list) or len(ring) < MIN_LINEAR_RING_POSITIONS:
        raise DocumentValidationError(
            [f"{geometry_type} {path} must contain at least four positions"]
        )
    return [
        _transform_position(
            position,
            transformer,
            geometry_type=geometry_type,
            path=f"{path} position {position_index}",
        )
        for position_index, position in enumerate(ring)
    ]


def _transform_position(
    position: Any,
    transformer: Transformer,
    *,
    geometry_type: str,
    path: str,
) -> list[float]:
    if (
        not isinstance(position, list)
        or not MIN_POSITION_DIMENSIONS <= len(position) <= MAX_POSITION_DIMENSIONS
        or any(
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            for value in position
        )
    ):
        raise DocumentValidationError(
            [f"{geometry_type} {path} must contain two or three finite numbers"]
        )
    return list(transformer.transform(*position))


def _iter_positions(coordinates: Any) -> list[list[float]]:
    if not isinstance(coordinates, list):
        return []
    if coordinates and all(isinstance(value, int | float) for value in coordinates):
        return [coordinates]

    positions: list[list[float]] = []
    for child in coordinates:
        positions.extend(_iter_positions(child))
    return positions


async def import_features(
    features: list[PreparedFeature],
    *,
    client: httpx.AsyncClient,
    api_url: str,
) -> dict[str, Any]:
    """Upsert prepared features individually and return an import summary."""
    imported: list[dict[str, str]] = []
    for feature in features:
        url = f"{api_url}/collections/{feature.collection}/items:upsert"
        try:
            response = await client.post(
                url,
                json=feature.geojson,
                headers={"Content-Type": "application/geo+json"},
            )
        except httpx.HTTPError as err:
            raise UpstreamImportError(
                collection=feature.collection,
                feature_id=feature.feature_id,
                reason=f"request failed: {err}",
            ) from err
        if not response.is_success:
            raise UpstreamImportError(
                collection=feature.collection,
                feature_id=feature.feature_id,
                reason=f"upstream returned HTTP {response.status_code}",
            )
        try:
            response_body = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise UpstreamImportError(
                collection=feature.collection,
                feature_id=feature.feature_id,
                reason="successful upstream response did not contain valid JSON",
            ) from err
        upstream_id = (
            response_body.get("id") if isinstance(response_body, dict) else None
        )
        if not isinstance(upstream_id, str):
            raise UpstreamImportError(
                collection=feature.collection,
                feature_id=feature.feature_id,
                reason="successful upstream response requires a UUID string id",
            )
        try:
            stable_id = str(UUID(upstream_id))
        except ValueError as err:
            raise UpstreamImportError(
                collection=feature.collection,
                feature_id=feature.feature_id,
                reason="successful upstream response requires a UUID string id",
            ) from err
        imported.append({"collection": feature.collection, "id": stable_id})
    return {"total": len(imported), "features": imported}
