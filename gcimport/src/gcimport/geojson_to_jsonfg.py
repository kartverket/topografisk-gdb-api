"""Convert classic GeoJSON (with CRS) exports to JSON-FG for gcimport."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from gcimport.profiles.bane import BANE_PROFILE

_EPSG_URN = re.compile(
    r"^urn:ogc:def:crs:EPSG::(?P<code>\d+)$",
    re.IGNORECASE,
)
_EPSG_HTTP = re.compile(
    r"^https?://www\.opengis\.net/def/crs/EPSG/\d+/(?P<code>\d+)$",
    re.IGNORECASE,
)
_EPSG_PLAIN = re.compile(r"^EPSG:(?P<code>\d+)$", re.IGNORECASE)


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


def feature_type_from_objtype(objtype: Any) -> str:
    """Map FKB ``objtype`` to a Bane JSON-FG ``featureType``."""
    if not isinstance(objtype, str) or not objtype.strip():
        raise ConversionError("properties.objtype must be a non-empty string")
    collection = BANE_PROFILE.collection_for(objtype)
    if collection is None:
        raise ConversionError(
            f"properties.objtype must be one of {BANE_PROFILE.supported_feature_types}"
        )
    return collection


def convert_feature(feature: Any, *, index: int) -> dict[str, Any]:
    """Convert one classic GeoJSON feature to JSON-FG."""
    if not isinstance(feature, dict):
        raise ConversionError(f"features[{index}] must be an object")
    if feature.get("type") != "Feature":
        raise ConversionError(f"features[{index}].type must be 'Feature'")

    properties = feature.get("properties")
    if not isinstance(properties, dict):
        raise ConversionError(f"features[{index}].properties must be an object")

    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise ConversionError(f"features[{index}].geometry must be an object")
    if geometry.get("type") != BANE_PROFILE.geometry_type:
        raise ConversionError(
            f"features[{index}].geometry.type must be '{BANE_PROFILE.geometry_type}'"
        )
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list):
        raise ConversionError(
            f"features[{index}].geometry.coordinates must be an array"
        )

    try:
        feature_type = feature_type_from_objtype(properties.get("objtype"))
    except ConversionError as err:
        raise ConversionError(f"features[{index}]: {err}") from err

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
        convert_feature(feature, index=index) for index, feature in enumerate(features)
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
) -> dict[str, Any]:
    """Read GeoJSON from disk, convert, and optionally write JSON-FG."""
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ConversionError(f"could not read {source}: {err}") from err

    converted = convert_document(document, crs=crs)
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
            "for the gcimport Bane importer."
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
    args = parser.parse_args(argv)

    try:
        convert_file(args.source, args.output, crs=args.crs)
    except ConversionError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
