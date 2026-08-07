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
MIN_POSITION_DIMENSIONS = 2
MAX_POSITION_DIMENSIONS = 3


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
    identities: set[tuple[str, ...]] = set()

    for index, feature in enumerate(features):
        try:
            item = _prepare_feature(feature, inherited_crs, profile)
            identity = tuple(
                str(item.geojson["properties"][name])
                for name in profile.identity_fields
            )
            if identity in identities:
                errors.append(
                    f"features[{index}]: duplicate "
                    f"({', '.join(profile.identity_fields)})"
                )
            else:
                identities.add(identity)
            prepared.append(item)
        except DocumentValidationError as err:
            errors.extend(f"features[{index}]: {message}" for message in err.errors)

    if errors:
        raise DocumentValidationError(errors)
    return prepared


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
    if not isinstance(raw_feature_type, str):
        errors.append("featureType must be a string")
        collection = ""
    else:
        collection = profile.collection_for(raw_feature_type) or ""
        if not collection:
            errors.append(f"featureType must be {profile.supported_feature_types}")

    properties = feature.get("properties")
    if not isinstance(properties, dict):
        errors.append("properties must be an object")
        properties = {}

    if collection:
        missing = sorted(
            name
            for name in profile.required_fields[collection]
            if name not in properties or properties[name] is None
        )
        if missing:
            errors.append(f"missing required properties: {', '.join(missing)}")

    identity_values, identity_errors = _identity_values(properties, profile)
    errors.extend(identity_errors)

    try:
        geometry, source_crs = _select_geometry(feature, inherited_crs)
        transformed_geometry = _transform_geometry(
            geometry,
            source_crs,
            profile,
        )
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
) -> dict[str, Any]:
    if geometry.get("type") != profile.geometry_type:
        raise DocumentValidationError([f"geometry must be a {profile.geometry_type}"])
    if profile.geometry_type != "LineString":
        raise DocumentValidationError(
            [f"geometry type {profile.geometry_type} is not implemented"]
        )
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < MIN_LINESTRING_POSITIONS:
        raise DocumentValidationError(
            ["LineString coordinates must contain at least two positions"]
        )

    positions: list[tuple[float, ...]] = []
    for position_index, position in enumerate(coordinates):
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
                [
                    "LineString position "
                    f"{position_index} must contain two or three finite numbers"
                ]
            )
        positions.append(tuple(position))

    try:
        transformer = Transformer.from_crs(
            CRS.from_user_input(source_crs),
            CRS.from_user_input(profile.target_crs),
            always_xy=True,
        )
        transformed = [list(transformer.transform(*position)) for position in positions]
    except (CRSError, ProjError) as err:
        raise DocumentValidationError(
            [f"cannot transform coordRefSys '{source_crs}' to {profile.target_crs}"]
        ) from err

    if any(not math.isfinite(value) for position in transformed for value in position):
        raise DocumentValidationError(
            [f"coordinate transform from '{source_crs}' produced invalid values"]
        )
    return {"type": "LineString", "coordinates": transformed}


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
