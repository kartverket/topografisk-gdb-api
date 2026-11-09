"""Convert a QMS JSON file and a domain YAML file to a geocomponents dataset
description YAML.

The domain YAML file supplies SRID, Z coordinates, outward identifiers, and
server-managed fields. Norwegian characters in identifiers are transliterated
(ø→o, æ→e, å→a).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Identifier normalisation
# ---------------------------------------------------------------------------
_TRANSLIT = str.maketrans(
    "øæåØÆÅ",
    "oeaOEA",
)

_OUTWARD_IDENTIFIER = "outward_identifier"
_FKB_ATTRIBUTE_STRUCT_DEPTH = 2
_SERVER_MANAGED = "server_managed"


# Prevents anchors and aliases in the YAML output.
class NoAliasSafeDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _safe_id(raw: str) -> str:
    """Lowercase + transliterate Norwegian chars → SafeIdentifier.

    Non-ASCII characters that remain after transliteration are replaced with
    underscores. Result is capped at 40 characters (SafeIdentifier max length).
    """
    s = raw.translate(_TRANSLIT).lower()
    s = re.sub(r"[^a-z0-9_]", "_", s)
    s = s.lstrip("0123456789_") or "x"
    return s[:40]


# ---------------------------------------------------------------------------
# Type mappings
# ---------------------------------------------------------------------------
_QMS_SCALAR_TYPES: dict[str, str] = {
    "String": "string",
    "URI": "string",
    "Integer": "integer",
    "DateTime": "timestamp",
    "Date": "date",
    "Boolean": "boolean",
    "Real": "number",
    "Number": "number",
}

_SOSI_TO_WKT: dict[str, str] = {
    "GM_Curve": "MultiLineString",
    "GM_Point": "MultiPoint",
    "GM_Surface": "MultiPolygon",
    "GM_MultiCurve": "MultiLineString",
    "GM_MultiPoint": "MultiPoint",
    "GM_MultiSurface": "MultiPolygon",
}


# ---------------------------------------------------------------------------
# Core conversion helpers
# ---------------------------------------------------------------------------
def _build_dat_lookup(data: dict) -> dict[str, dict]:
    """UUID → DAT entry map for fast lookup."""
    return {entry["UUID"]: entry for entry in data.get("DefaultAttributeTypes", [])}


def _convert_attr(
    attr: dict,
    dat_by_uuid: dict[str, dict],
    codelists: dict[str, dict],  # name → codelist dict; mutated
) -> dict | None:
    """Convert one QMS AttributeType entry to a geocomponents field dict.

    Returns None when the type is unknown or the attribute should be omitted.
    Codelists discovered are registered into *codelists* (keyed by name, deduped).
    """
    qms_type = attr.get("Type", "")
    name = _safe_id(attr["Name"])
    required = attr.get("MultiplicityMin", 0) >= 1

    if qms_type == "CodeList":
        dat = dat_by_uuid.get(attr.get("UUID", ""))
        if dat and dat.get("CodeList"):
            cl_name = _safe_id(dat["TypeName"])
            if cl_name not in codelists:
                codelists[cl_name] = {
                    "name": cl_name,
                    "values": [{"code": v["Value"]} for v in dat["CodeList"]],
                }
            fld: dict = {"name": name, "codelist": cl_name}
        else:
            fld = {"name": name, "type": "string"}
        if required:
            fld["required"] = True
        return fld

    if qms_type == "Struct":
        sub_attrs = attr.get("AttributeTypes", [])
        sub_fields = []
        for sub in sub_attrs:
            sf = _convert_attr(sub, dat_by_uuid, codelists)
            if sf:
                sub_fields.append(sf)
        fld = {"name": name, "type": "object"}
        if required:
            fld["required"] = True
        fld["fields"] = sub_fields
        return fld

    geocomponents_type = _QMS_SCALAR_TYPES.get(qms_type)
    if geocomponents_type is None:
        return None
    fld = {"name": name, "type": geocomponents_type}
    if required:
        fld["required"] = True
    return fld


def _convert_feature_type(
    ft: dict,
    domain: dict,
    dat_by_uuid: dict[str, dict],
    codelists: dict[str, dict],
) -> dict:
    """Convert one QMS FeatureType to a geocomponents collection dict."""
    collection_name, collection = parse_qms_collection(
        ft, dat_by_uuid, codelists, _safe_id
    )

    if domain.get("general") is None:
        raise Exception("General section must be specified in the domain file")
    general_domain_settings = parse_domain_general(domain.get("general"), _safe_id)
    _collection_name_from_domain, collection_domain_settings = parse_domain_collection(
        collection_name,
        domain.get("collections", {}).get(collection_name, {}),
        _safe_id,
    )

    for setting, value in collection_domain_settings.items():
        if isinstance(value, dict):
            for sub_setting, _sub_value in value.items():
                if (
                    general_domain_settings.get(setting) is not None
                    and general_domain_settings[setting].get(sub_setting) is not None
                ):
                    raise Exception(
                        f"Collection domain setting '{setting}.{sub_setting}' conflicts with general domain setting"
                    )
        elif general_domain_settings.get(setting) is not None:
            raise Exception(
                f"Collection domain setting '{setting}' conflicts with general domain setting"
            )

    collection["geometry"]["srid"] = general_domain_settings["srid"]
    collection["geometry"]["has_z"] = general_domain_settings["has_z"]

    outward_identifer = collection_domain_settings.get(
        _OUTWARD_IDENTIFIER
    ) or general_domain_settings.get(_OUTWARD_IDENTIFIER)
    if outward_identifer is not None:
        collection["outward_identifier"] = outward_identifer

    server_managed = {}
    for key, value in collection_domain_settings.get("server_managed", {}).items():
        server_managed[key] = value
    for key, value in general_domain_settings.get("server_managed", {}).items():
        server_managed[key] = value
    collection["server_managed"] = server_managed

    return collection


def parse_qms_collection(
    collection: dict,
    dat_by_uuid: dict[str, dict],
    codelists: dict[str, dict],
    normalizer: Callable[[str], str],
) -> tuple[str, dict]:
    """Build a collection description with only the normalized fields emitted from QMS.

    returns (collection_name, normalised_collection_description)
    """
    name = normalizer(collection["Name"])
    description = collection.get("Description", "")

    geo_types = collection.get("GeometryTypes")
    if geo_types is None:
        raise Exception("No geometry type specified for feature type")
    geo_type_sosi = geo_types[0]["Type"]
    geo_type = _SOSI_TO_WKT.get(geo_type_sosi)

    fields: list[dict] = []
    for attr in collection.get("AttributeTypes", []):
        field = _convert_attr(attr, dat_by_uuid, codelists)
        if field:
            fields.append(field)

    normalized_collection: dict = {
        "name": name,
        "title": collection["Name"],
        "description": description,
        "geometry": {"type": geo_type},
        "fields": fields,
    }

    return name, normalized_collection


def parse_domain_general(settings: dict, normalizer: Callable[[str], str]) -> dict:
    """Normalize field paths in general domain settings.

    returns normalised_settings
    """
    srid = settings.get("srid")
    if srid is None:
        raise ValueError("SRID must be specified in the general domain settings")
    has_z = settings.get("has_z")
    if has_z is None:
        raise ValueError("has_z must be specified in the general domain settings")

    outward_identifier = settings.get(_OUTWARD_IDENTIFIER)
    if outward_identifier is not None:
        outward_identifier = normalizer(outward_identifier)

    server_managed = settings.get(_SERVER_MANAGED)
    if server_managed is not None:
        for key, value in server_managed.items():
            server_managed[key] = normalizer(value)

    normalized_settings = {
        "srid": srid,
        "has_z": has_z,
    }
    if outward_identifier is not None:
        normalized_settings[_OUTWARD_IDENTIFIER] = outward_identifier
    if server_managed is not None:
        normalized_settings[_SERVER_MANAGED] = server_managed

    return normalized_settings


def parse_domain_collection(
    name: str, settings: dict, normalizer: Callable[[str], str]
) -> tuple[str, dict]:
    """Normalise collection name and collection-specific settings.

    returns (collection_name, normalised_settings)
    """
    name = normalizer(name)

    outward_identifier = settings.get(_OUTWARD_IDENTIFIER)
    if outward_identifier is not None:
        outward_identifier = normalizer(outward_identifier)

    server_managed = settings.get(_SERVER_MANAGED)
    if server_managed is not None:
        for key, value in server_managed.items():
            server_managed[key] = normalizer(value)

    normalized_collection = {}
    if outward_identifier is not None:
        normalized_collection[_OUTWARD_IDENTIFIER] = outward_identifier
    if server_managed is not None:
        normalized_collection[_SERVER_MANAGED] = server_managed

    return name, normalized_collection


def _get_outward_identifier(ft: dict, general: dict, collection: dict) -> str | None:
    if _OUTWARD_IDENTIFIER in general and _OUTWARD_IDENTIFIER in collection:
        raise ValueError(
            f"{_OUTWARD_IDENTIFIER} is defined in both general and collections.{_safe_id(ft['Name'])}"
        )

    outward_identifier = collection.get(
        _OUTWARD_IDENTIFIER, general.get(_OUTWARD_IDENTIFIER)
    )

    if not outward_identifier:
        return None

    outward_identifier_array = outward_identifier.split(".")

    outward_identifier_present = False
    for attribute in ft["AttributeTypes"]:
        if len(outward_identifier_array) == _FKB_ATTRIBUTE_STRUCT_DEPTH:
            if (
                _safe_id(attribute["Name"]) == _safe_id(outward_identifier_array[0])
                and "AttributeTypes" in attribute
                and any(
                    _safe_id(sub_attr["Name"]) == _safe_id(outward_identifier_array[1])
                    for sub_attr in attribute["AttributeTypes"]
                )
            ):
                outward_identifier_present = True
                break
        elif len(outward_identifier_array) == 1 and _safe_id(
            attribute["Name"]
        ) == _safe_id(outward_identifier_array[0]):
            outward_identifier_present = True
            break

    if not outward_identifier_present:
        raise ValueError(
            f"{_OUTWARD_IDENTIFIER} references a non-existent path '{outward_identifier}' in feature {_safe_id(ft['Name'])}"
        )

    return outward_identifier


def _get_server_managed(ft: dict, general: dict, collection: dict) -> dict | None:
    for key in collection.get(_SERVER_MANAGED, {}):
        if key in general.get(_SERVER_MANAGED, {}):
            raise ValueError(
                f"{_SERVER_MANAGED}.{key} is defined in both general and collections.{_safe_id(ft['Name'])}"
            )

    server_managed = {}
    for key in collection.get(_SERVER_MANAGED, {}):
        server_managed[key] = collection[_SERVER_MANAGED][key]
    for key in general.get(_SERVER_MANAGED, {}):
        server_managed[key] = general[_SERVER_MANAGED][key]

    if not server_managed:
        return None

    server_managed_list = []
    for key in server_managed:
        server_managed_list.append(key.split("."))

    server_managed_present = [False] * len(server_managed_list)
    for i, key in enumerate(server_managed_list):
        for attribute in ft["AttributeTypes"]:
            if len(key) == _FKB_ATTRIBUTE_STRUCT_DEPTH:
                if (
                    _safe_id(attribute["Name"]) == _safe_id(key[0])
                    and "AttributeTypes" in attribute
                    and any(
                        _safe_id(sub_attr["Name"]) == _safe_id(key[1])
                        for sub_attr in attribute["AttributeTypes"]
                    )
                ):
                    server_managed_present[i] = True
                    break
            elif len(key) == 1 and _safe_id(attribute["Name"]) == _safe_id(key[0]):
                server_managed_present[i] = True
                break

    if not all(server_managed_present):
        raise ValueError(
            f"{_SERVER_MANAGED} references a non-existent path in feature {_safe_id(ft['Name'])}"
        )

    return server_managed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def convert_qms(data: dict, domain: dict, dataset_name: str) -> str:
    """Convert a QMS schema dict to a geocomponents dataset YAML string."""
    dat_by_uuid = _build_dat_lookup(data)
    codelists: dict[str, dict] = {}
    collections = []

    for ft in data.get("FeatureTypes", []):
        collections.append(_convert_feature_type(ft, domain, dat_by_uuid, codelists))

    obj_katalog = data.get("Objektkatalog", {})
    title = obj_katalog.get("ObjektkatalogFullstendigNavn") or dataset_name
    version = obj_katalog.get("Versjon", "")
    description = f"{title} {version}".strip() if version else title

    dataset: dict = {
        "name": dataset_name,
        "title": title,
        "description": description,
        "collections": collections,
        "codelists": list(codelists.values()),
    }
    return yaml.dump(
        dataset,
        Dumper=NoAliasSafeDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )


# ---------------------------------------------------------------------------
# CLI entry point (python -m geocomponents.convert)
# ---------------------------------------------------------------------------
def _cli_main() -> None:  # pragma: no cover
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Convert a QMS JSON schema to a geocomponents dataset YAML."
    )
    parser.add_argument("--uml", required=True, type=Path, help="QMS JSON input file")
    parser.add_argument(
        "--domain", required=True, type=Path, help="Domain YAML input file"
    )
    parser.add_argument("--output", required=True, type=Path, help="YAML output file")
    parser.add_argument(
        "--dataset-name", required=True, help="Dataset identifier (SafeIdentifier)"
    )
    args = parser.parse_args()

    data = json.loads(args.uml.read_text(encoding="utf-8"))
    domain = yaml.safe_load(args.domain.read_text(encoding="utf-8"))
    yaml_str = convert_qms(data, domain, args.dataset_name)
    args.output.write_text(yaml_str, encoding="utf-8")
    sys.stderr.write(f"Written: {args.output}\n")


if __name__ == "__main__":  # pragma: no cover
    _cli_main()
