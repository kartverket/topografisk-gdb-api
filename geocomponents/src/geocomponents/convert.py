"""Convert a QMS JSON file and a domain YAML file to a geocomponents dataset
description YAML.

The domain YAML file supplies SRID, Z coordinates, outward identifiers, and
server-managed fields. Norwegian characters in identifiers are transliterated
(ø→o, æ→e, å→a).
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Mapping
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
    normalizer: callable[[str], str],
) -> dict | None:
    """Convert one QMS AttributeType entry to a geocomponents field dict.

    Returns None when the type is unknown or the attribute should be omitted.
    Codelists discovered are registered into *codelists* (keyed by name, deduped).
    """
    qms_type = attr.get("Type", "")
    name = normalizer(attr["Name"])
    required = attr.get("MultiplicityMin", 0) >= 1

    if qms_type == "CodeList":
        dat = dat_by_uuid.get(attr.get("UUID", ""))
        if dat and dat.get("CodeList"):
            cl_name = normalizer(dat["TypeName"])
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
            sf = _convert_attr(sub, dat_by_uuid, codelists, normalizer)
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
    normalizer: Callable[[str], str],
) -> dict:
    """Convert one QMS FeatureType to a geocomponents collection dict."""
    collection_name, collection = _parse_qms_collection(
        ft, dat_by_uuid, codelists, normalizer
    )

    collection["geometry"]["srid"] = domain["general"]["srid"]
    collection["geometry"]["has_z"] = domain["general"]["has_z"]

    outward_identifer = domain.get("collections", {}).get(collection_name, {}).get(
        _OUTWARD_IDENTIFIER
    ) or domain["general"].get(_OUTWARD_IDENTIFIER)
    if outward_identifer is not None:
        if not _outward_identifier_exists_in_qms(collection, outward_identifer):
            raise Exception(
                f"{outward_identifer} references a non-existent path in feature {collection['name']}"
            )
        collection[_OUTWARD_IDENTIFIER] = outward_identifer

    server_managed = {}
    for key, value in (
        domain.get("collections", {})
        .get(collection_name, {})
        .get("server_managed", {})
        .items()
    ):
        server_managed[key] = value
    for key, value in domain["general"].get("server_managed", {}).items():
        server_managed[key] = value

    if server_managed != {}:
        if not _server_managed_exists_in_qms(collection, server_managed):
            raise Exception(
                f"{server_managed} references a non-existent path in feature {collection['name']}"
            )
        collection["server_managed"] = server_managed

    return collection


def _compare_settings(general_setting: dict, collection_setting: dict):
    for setting, value in collection_setting.items():
        if isinstance(value, dict):
            _compare_settings(general_setting.get(setting, {}), value)
        elif general_setting.get(setting) is not None:
            raise Exception(
                f"Collection domain setting '{setting}' conflicts with general domain setting"
            )


def _parse_outward_identifier(
    outward_identifier: str, normalizer: Callable[[str], str]
) -> str | None:
    outward_identifier_array = outward_identifier.split(".")
    normalised_identifier_array = []
    for identifier_part in outward_identifier_array:
        normalised_identifier_array.append(normalizer(identifier_part))
    return ".".join(normalised_identifier_array)


def _domain_pre_validation(domain: dict) -> None:
    if domain.get("general") is None:
        raise Exception("General section must be specified in the domain file")
    if domain["general"].get("srid") is None:
        raise ValueError("SRID must be specified in the general domain settings")
    if domain["general"].get("has_z") is None:
        raise ValueError("has_z must be specified in the general domain settings")


def _domain_post_validation(domain: dict) -> None:
    general = domain["general"]
    for collection in domain.get("collections", {}).values():
        if _OUTWARD_IDENTIFIER in general and _OUTWARD_IDENTIFIER in collection:
            raise ValueError(
                "Collection domain setting 'outward_identifier' conflicts with general domain setting"
            )

        duplicate_paths = (
            general.get(_SERVER_MANAGED, {}).keys()
            & collection.get(_SERVER_MANAGED, {}).keys()
        )
        if duplicate_paths:
            path = sorted(duplicate_paths)[0]
            raise ValueError(
                f"Collection domain setting '{path}' conflicts with general domain setting"
            )


def _parse_qms_collection(
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
        field = _convert_attr(attr, dat_by_uuid, codelists, normalizer)
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


def _outward_identifier_exists_in_qms(
    collection: dict, outward_identifier: str
) -> bool:
    outward_identifier_array = outward_identifier.split(".")
    for attribute in collection["fields"]:
        if len(outward_identifier_array) > 1:
            if (
                attribute["name"] == outward_identifier_array[0]
                and "fields" in attribute
                and any(
                    sub_attr["name"] == outward_identifier_array[1]
                    for sub_attr in attribute["fields"]
                )
            ):
                return True
        elif (
            len(outward_identifier_array) == 1
            and attribute["name"] == outward_identifier_array[0]
        ):
            return True
    return False


def _server_managed_exists_in_qms(collection: dict, server_managed: dict) -> bool:
    server_managed_list = []
    for key in server_managed:
        server_managed_list.append(key.split("."))

    server_managed_present = [False] * len(server_managed_list)
    for i, key in enumerate(server_managed_list):
        for attribute in collection["fields"]:
            if len(key) > 1:
                if (
                    attribute["name"] == key[0]
                    and "fields" in attribute
                    and any(
                        sub_attr["name"] == key[1] for sub_attr in attribute["fields"]
                    )
                ):
                    server_managed_present[i] = True
                    break
            elif len(key) == 1 and attribute["name"] == key[0]:
                server_managed_present[i] = True
                break

    return all(server_managed_present)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def convert_qms(data: dict, domain_raw: dict, dataset_name: str) -> str:
    """Convert a QMS schema dict to a geocomponents dataset YAML string."""
    dat_by_uuid = _build_dat_lookup(data)
    codelists: dict[str, dict] = {}
    collections = []

    _domain_pre_validation(domain_raw)
    domain = _normalize_tree(domain_raw, _safe_id)
    _domain_post_validation(domain)

    for ft in data.get("FeatureTypes", []):
        collections.append(
            _convert_feature_type(ft, domain, dat_by_uuid, codelists, _safe_id)
        )

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


def _normalize_tree(obj, normalizer):
    if isinstance(obj, Mapping):
        result = {}
        for key, value in obj.items():
            if normalizer(key) == _OUTWARD_IDENTIFIER:
                result[_OUTWARD_IDENTIFIER] = _parse_outward_identifier(
                    value, normalizer
                )
                continue
            if normalizer(key) == _SERVER_MANAGED:
                normalized_paths = {}
                for path, strategy in value.items():
                    normalized_path = ".".join(
                        normalizer(part) for part in path.split(".")
                    )
                    if normalized_path in normalized_paths:
                        raise ValueError(
                            f"Key collision after normalization: {normalized_path!r}"
                        )
                    normalized_paths[normalized_path] = _normalize_tree(
                        strategy, normalizer
                    )
                result[_SERVER_MANAGED] = normalized_paths
                continue
            new_key = _normalize_tree(key, normalizer)
            if new_key in result:
                raise ValueError(f"Key collision after normalization: {new_key!r}")
            result[new_key] = _normalize_tree(value, normalizer)
        return result

    if isinstance(obj, list):
        return [_normalize_tree(item, normalizer) for item in obj]

    if isinstance(obj, tuple):
        return tuple(_normalize_tree(item, normalizer) for item in obj)

    if isinstance(obj, set):
        return {_normalize_tree(item, normalizer) for item in obj}

    if isinstance(obj, int):
        return obj

    return normalizer(obj)


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
