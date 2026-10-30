"""Convert a QMS (SOSI Quality Metadata Schema) JSON file to a geocomponents
dataset description YAML.

Tested against FKB-format QMS files (FKB-Bane 5.0). FKB-specific conventions:
- Struct with DAT TypeName "Identifikasjon" → outward_identifier + server_managed versjonId.
- Field with DAT TypeName "oppdateringsdato" → server_managed timestamp_iso.
- Geometry GM_Curve → LineString.
- Norwegian characters in identifiers are transliterated (ø→o, æ→ae, å→a).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Identifier normalisation
# ---------------------------------------------------------------------------
_TRANSLIT = str.maketrans(
    "øæåØÆÅéèêëàáâäíìîïóòôöúùûü",
    "oaeOAEeeeeaaaaiiiioooouuuu",
)


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

_GM_TO_GEOCOMPONENTS: dict[str, str] = {
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
    domain: dict | None,
    dat_by_uuid: dict[str, dict],
    codelists: dict[str, dict],
) -> dict:
    """Convert one QMS FeatureType to a geocomponents collection dict."""
    coll_name = _safe_id(ft["Name"])
    description = ft.get("Description", "")

    geo_types = ft.get("GeometryTypes", [])
    gm_type = geo_types[0]["Type"] if geo_types else "GM_Curve"
    geom_type = _GM_TO_GEOCOMPONENTS.get(gm_type, "LineString")

    fields: list[dict] = []
    outward_identifier: str | None = None
    if domain is not None:
        outward_identifier = (
            domain.get("collections", {}).get(coll_name, {}).get("outward_identifier")
            if domain.get("collections", {})
            .get(coll_name, {})
            .get("outward_identifier")
            is not None
            else domain.get("general").get("outward_identifier")
            if domain.get("general").get("outward_identifier") is not None
            else None
        )

    server_managed: dict[str, str] = {}
    if domain is not None:
        server_managed = (
            domain.get("collections", {}).get(coll_name, {}).get("server_managed", {})
            if domain.get("collections", {}).get(coll_name, {}).get("server_managed")
            is not None
            else domain.get("general").get("server_managed", {})
            if domain.get("general").get("server_managed") is not None
            else {}
        )

    srid: int = domain.get("general", {}).get("srid", 4326) if domain else 4326
    has_z: bool = domain.get("general", {}).get("has_z", False) if domain else False

    for attr in ft.get("AttributeTypes", []):
        fld = _convert_attr(attr, dat_by_uuid, codelists)
        if fld:
            fields.append(fld)

    coll: dict = {
        "name": coll_name,
        "title": ft["Name"],
        "description": description,
        "geometry": {"type": geom_type, "srid": srid, "has_z": has_z},
    }
    if outward_identifier:
        coll["outward_identifier"] = outward_identifier
    if server_managed:
        coll["server_managed"] = server_managed
    coll["fields"] = fields
    return coll


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def convert_qms(data: dict, domain: dict | None, dataset_name: str) -> str:
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
# CLI entry point  (python -m geocomponents.convert or via typer in cli.py)
# ---------------------------------------------------------------------------
def _cli_main() -> None:  # pragma: no cover
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Convert a QMS JSON schema to a geocomponents dataset YAML."
    )
    parser.add_argument("--uml", required=True, type=Path, help="QMS JSON input file")
    parser.add_argument("--domain", type=Path, help="Domain YAML input file")
    parser.add_argument("--output", required=True, type=Path, help="YAML output file")
    parser.add_argument(
        "--dataset-name", required=True, help="Dataset identifier (SafeIdentifier)"
    )
    args = parser.parse_args()

    data = json.loads(args.uml.read_text(encoding="utf-8"))
    domain = (
        yaml.safe_load(args.domain.read_text(encoding="utf-8"))
        if args.domain is not None
        else None
    )
    yaml_str = convert_qms(data, domain, args.dataset_name)
    args.output.write_text(yaml_str, encoding="utf-8")
    sys.stderr.write(f"Written: {args.output}\n")


if __name__ == "__main__":  # pragma: no cover
    _cli_main()
