"""Convert classic GeoJSON (with CRS) exports to JSON-FG for gcimport."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from gcimport.profiles import BANE_PROFILE, BUILTIN_PROFILES, ImportProfile, get_profile

_EPSG_URN = re.compile(
    r"^urn:ogc:def:crs:EPSG::(?P<code>\d+)$",
    re.IGNORECASE,
)
_EPSG_HTTP = re.compile(
    r"^https?://www\.opengis\.net/def/crs/EPSG/\d+/(?P<code>\d+)$",
    re.IGNORECASE,
)
_EPSG_PLAIN = re.compile(r"^EPSG:(?P<code>\d+)$", re.IGNORECASE)

_PROPERTY_ALIASES: dict[str, str] = {
    # Identity fields seen in upstream exports.
    "navnerom": "identifikasjon_navnerom",
    "versjonid": "identifikasjon_versjonid",
    # Quality fields seen without the quality prefix.
    "datafangstmetode": "kvalitet_datafangstmetode",
    "noyaktighet": "kvalitet_noyaktighet",
    "synbarhet": "kvalitet_synbarhet",
    "datafangstmetodehoyde": "kvalitet_datafangstmetodehoyde",
    "noyaktighethoyde": "kvalitet_noyaktighethoyde",
}


class ConversionError(ValueError):
    """Raised when the source GeoJSON cannot be converted."""


def normalize_crs(value: str) -> str:
    """Normalize common CRS strings to ``EPSG:<code>``."""
    text = value.strip()
    for pattern in (_EPSG_URN, _EPSG_HTTP, _EPSG_PLAIN):
        match = pattern.fullmatch(text)
        if match:
            return f"EPSG:{match.group('code')}"
    raise ConversionError(f"unsupported CRS '{value}'")


def crs_from_geojson(document: dict[str, Any]) -> str | None:
    """Read a classic GeoJSON ``crs`` member, if present."""
    crs = document.get("crs")
    if crs is None:
        return None
    if not isinstance(crs, dict):
        raise ConversionError("crs must be an object")
    if crs.get("type") != "name":
        raise ConversionError("crs.type must be 'name'")
    properties = crs.get("properties")
    if not isinstance(properties, dict):
        raise ConversionError("crs.properties must be an object")
    name = properties.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConversionError("crs.properties.name must be a non-empty string")
    return normalize_crs(name)


def feature_type_from_objtype(
    objtype: Any,
    geometry_type: Any,
    profile: ImportProfile,
) -> str:
    """Map FKB ``objtype`` to a profile-specific JSON-FG ``featureType``."""
    if not isinstance(objtype, str) or not objtype.strip():
        raise ConversionError("properties.objtype must be a non-empty string")
    if not isinstance(geometry_type, str) or not geometry_type.strip():
        raise ConversionError("geometry.type must be a non-empty string")
    collection = profile.collection_for_objtype(objtype, geometry_type)
    if collection is None:
        raise ConversionError(
            _unsupported_objtype_message(objtype, geometry_type, profile)
        )
    return collection


def _unsupported_objtype_message(
    objtype: str,
    geometry_type: str,
    profile: ImportProfile,
) -> str:
    candidates = profile.collections_for_objtype(objtype)
    if candidates:
        supported_geometry_types = " or ".join(
            sorted(
                {
                    profile.geometry_type_for_collection(collection)
                    for collection in candidates
                }
            )
        )
        return (
            f"properties.objtype '{objtype}' requires geometry.type "
            f"{supported_geometry_types}; got '{geometry_type}'"
        )

    message = f"properties.objtype must be one of {profile.supported_objtypes}"
    matching_profiles = [
        candidate.name
        for candidate in BUILTIN_PROFILES.values()
        if candidate.name != profile.name and candidate.collections_for_objtype(objtype)
    ]
    if len(matching_profiles) == 1:
        return f"{message}; '{objtype}' belongs to the {matching_profiles[0]} profile"
    return message


def normalize_properties(properties: dict[str, Any]) -> dict[str, Any]:
    """Copy known source aliases into canonical property names when missing."""
    normalized = dict(properties)
    for source_name, target_name in _PROPERTY_ALIASES.items():
        if target_name in normalized:
            continue
        if source_name in normalized:
            normalized[target_name] = normalized[source_name]
    return normalized


def normalize_geometry_for_profile(
    geometry: dict[str, Any],
    *,
    profile: ImportProfile,
    collection: str,
    index: int,
) -> dict[str, Any]:
    """Normalize known geometry variants for the active profile."""
    geometry_type = geometry.get("type")
    target_geometry_type = profile.geometry_type_for_collection(collection)
    if geometry_type == target_geometry_type:
        return geometry

    if geometry_type == "LineString" and target_geometry_type == "MultiLineString":
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list):
            raise ConversionError(
                f"features[{index}].geometry.coordinates must be an array"
            )
        return {
            "type": "MultiLineString",
            "coordinates": [coordinates],
        }

    if geometry_type == "MultiLineString" and target_geometry_type == "LineString":
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list):
            raise ConversionError(
                f"features[{index}].geometry.coordinates must be an array"
            )
        if len(coordinates) != 1:
            raise ConversionError(
                f"features[{index}].geometry.coordinates for MultiLineString "
                "must contain exactly one part"
            )
        part = coordinates[0]
        if not isinstance(part, list):
            raise ConversionError(
                f"features[{index}].geometry.coordinates[0] must be an array"
            )
        return {
            "type": "LineString",
            "coordinates": part,
        }

    if geometry_type == "MultiLineString" and target_geometry_type == "MultiPolygon":
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list):
            raise ConversionError(
                f"features[{index}].geometry.coordinates must be an array"
            )
        if not coordinates:
            raise ConversionError(
                f"features[{index}].geometry.coordinates must contain at least one part"
            )
        for part_index, part in enumerate(coordinates):
            if not isinstance(part, list):
                raise ConversionError(
                    f"features[{index}].geometry.coordinates[{part_index}] must be an array"
                )
        return {
            "type": "MultiPolygon",
            "coordinates": [[part] for part in coordinates],
        }

    raise ConversionError(
        f"features[{index}].geometry.type must be '{target_geometry_type}'"
    )


def convert_feature(
    feature: Any,
    *,
    profile: ImportProfile = BANE_PROFILE,
    index: int,
) -> dict[str, Any]:
    """Convert one classic GeoJSON feature to JSON-FG."""
    if not isinstance(feature, dict):
        raise ConversionError(f"features[{index}] must be an object")
    if feature.get("type") != "Feature":
        raise ConversionError(f"features[{index}].type must be 'Feature'")

    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise ConversionError(f"features[{index}].properties must be an object")
    properties = normalize_properties(properties)

    try:
        feature_type = feature_type_from_objtype(
            properties.get("objtype"),
            feature.get("geometry", {}).get("type")
            if isinstance(feature.get("geometry"), dict)
            else None,
            profile,
        )
    except ConversionError as err:
        raise ConversionError(f"features[{index}]: {err}") from err

    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise ConversionError(f"features[{index}].geometry must be an object")
    geometry = normalize_geometry_for_profile(
        geometry,
        profile=profile,
        collection=feature_type,
        index=index,
    )
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list):
        raise ConversionError(
            f"features[{index}].geometry.coordinates must be an array"
        )

    converted: dict[str, Any] = {
        "type": "Feature",
        "featureType": feature_type,
        "place": {
            "type": geometry["type"],
            "coordinates": coordinates,
        },
        "properties": properties,
    }
    if "id" in feature:
        converted["id"] = feature["id"]
    return converted


def convert_document(
    document: Any,
    *,
    crs: str | None = None,
    profile: ImportProfile = BANE_PROFILE,
) -> dict[str, Any]:
    """Convert a classic GeoJSON FeatureCollection to JSON-FG."""
    if not isinstance(document, dict):
        raise ConversionError("document must be a JSON object")
    if document.get("type") != "FeatureCollection":
        raise ConversionError("type must be 'FeatureCollection'")

    features = document.get("features")
    if not isinstance(features, list):
        raise ConversionError("features must be an array")

    resolved_crs = crs
    if resolved_crs is None:
        resolved_crs = crs_from_geojson(document)
    else:
        resolved_crs = normalize_crs(resolved_crs)
    if resolved_crs is None:
        raise ConversionError("missing CRS; provide a GeoJSON crs member")

    converted_features = [
        convert_feature(feature, profile=profile, index=index)
        for index, feature in enumerate(features)
    ]
    return {
        "type": "FeatureCollection",
        "coordRefSys": resolved_crs,
        "features": converted_features,
    }


def convert_file(
    source: Path,
    destination: Path | None = None,
    *,
    crs: str | None = None,
    profile: ImportProfile = BANE_PROFILE,
) -> dict[str, Any]:
    """Read GeoJSON from disk, convert, and optionally write JSON-FG."""
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ConversionError(f"could not read {source}: {err}") from err

    converted = convert_document(document, crs=crs, profile=profile)
    payload = json.dumps(converted, ensure_ascii=False, indent=2) + "\n"
    if destination is None:
        sys.stdout.write(payload)
    else:
        destination.write_text(payload, encoding="utf-8")
    return converted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Convert classic GeoJSON (QGIS/ESRI-style CRS + objtype) to JSON-FG "
            "for a gcimport dataset profile."
        )
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Input GeoJSON FeatureCollection path",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output JSON-FG path (default: stdout)",
    )
    parser.add_argument(
        "--crs",
        help="Override CRS as EPSG:<code> (default: read from GeoJSON crs)",
    )
    parser.add_argument(
        "--profile",
        default=BANE_PROFILE.name,
        choices=sorted(BUILTIN_PROFILES),
        help=f"Built-in profile name (default: {BANE_PROFILE.name})",
    )
    args = parser.parse_args(argv)

    try:
        convert_file(
            args.source,
            args.output,
            crs=args.crs,
            profile=get_profile(args.profile),
        )
    except ConversionError as err:
        sys.stderr.write(f"error: {err}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
