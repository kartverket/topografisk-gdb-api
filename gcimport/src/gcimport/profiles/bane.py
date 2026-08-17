"""Import rules for the FKB-Bane dataset."""

from gcimport.profiles.base import ImportProfile

_COMMON_REQUIRED_FIELDS = frozenset(
    {
        "lokalid",
        "identifikasjon_navnerom",
        "oppdateringsdato",
        "datafangstdato",
        "medium",
    }
)

_QUALITY_PROPERTY_NAMES = {
    "kvalitet_datafangstmetode": "datafangstmetode",
    "kvalitet_noyaktighet": "noyaktighet",
    "kvalitet_synbarhet": "synbarhet",
    "kvalitet_datafangstmetodehoyde": "datafangstmetodehoyde",
    "kvalitet_noyaktighethoyde": "noyaktighethoyde",
}

_IDENTIFIKASJON_PROPERTY_NAMES = {
    "lokalid": "lokalid",
    "identifikasjon_navnerom": "navnerom",
    "identifikasjon_versjonid": "versjonid",
}


def _nested_string_properties(
    properties: dict[str, object],
    aliases: dict[str, str],
) -> dict[str, object]:
    nested: dict[str, object] = {}
    for flat_name, nested_name in aliases.items():
        value = properties.get(flat_name)
        if isinstance(value, str):
            value = value.strip()
        if value:
            nested[nested_name] = value
    return nested


def _nested_properties(
    properties: dict[str, object],
    aliases: dict[str, str],
) -> dict[str, object]:
    return {
        nested_name: value
        for flat_name, nested_name in aliases.items()
        if (value := properties.get(flat_name)) is not None
    }


def _fkb_bane_upstream_properties(
    properties: dict[str, object],
    _collection: str,
) -> dict[str, object]:
    upstream = dict(properties)

    identifikasjon = _nested_string_properties(upstream, _IDENTIFIKASJON_PROPERTY_NAMES)
    if identifikasjon:
        upstream["identifikasjon"] = identifikasjon

    kvalitet = _nested_properties(upstream, _QUALITY_PROPERTY_NAMES)
    if kvalitet:
        upstream["kvalitet"] = kvalitet

    return upstream


BANE_PROFILE = ImportProfile(
    name="fkb_bane",
    title="FKB-Bane",
    dataset_api_path="/datasets/fkb_bane/ogc_api",
    target_crs="EPSG:5973",
    geometry_type="MultiLineString",
    collections={
        "jernbaneplattformkant": "jernbaneplattformkant",
        "spormidt": "spormidt",
    },
    required_fields={
        "jernbaneplattformkant": _COMMON_REQUIRED_FIELDS,
        "spormidt": _COMMON_REQUIRED_FIELDS
        | frozenset({"jernbanetype", "hoydereferanse"}),
    },
    identity_fields=("lokalid",),
    property_transform=_fkb_bane_upstream_properties,
)
