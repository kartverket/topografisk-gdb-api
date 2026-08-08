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

BANE_PROFILE = ImportProfile(
    name="bane",
    title="Bane",
    default_api_url="http://localhost:8000/datasets/bane/ogc_api",
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
    identity_fields=("lokalid", "identifikasjon_navnerom"),
)
