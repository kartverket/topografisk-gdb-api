"""Import rules for the FKB-Bygning dataset."""

from gcimport.profiles.base import ImportProfile

_LINE_SOURCE_OBJTYPES = (
    "bygning",
    "bygningbru",
    "bygningsavgrensningtiltak",
    "bygningsdelelinje",
    "bygningslinje",
    "fiktivbygningsavgrensning",
    "grunnmur",
    "låvebru",
    "mønelinje",
    "takkant",
    "takoverbyggkant",
    "takplatå",
    "taksprang",
    "taksprangbunn",
    "trappbygg",
    "veggfrittstående",
    "veranda",
)

_AREA_SOURCE_OBJTYPES = (
    "annenbygning",
    "bygning",
    "takoverbygg",
)

_SOURCE_OBJTYPES = _LINE_SOURCE_OBJTYPES

_COMMON_REQUIRED_FIELDS = frozenset(
    {
        "lokalid",
        "identifikasjon_navnerom",
        "oppdateringsdato",
        "datafangstdato",
    }
)

_COLLECTIONS: dict[str, str | tuple[str, ...]] = {
    **{objtype: "bygning" for objtype in _LINE_SOURCE_OBJTYPES},
    **{objtype: "bygning_omrade" for objtype in _AREA_SOURCE_OBJTYPES},
    "bygning": ("bygning", "bygning_omrade"),
}

BYGNING_PROFILE = ImportProfile(
    name="bygning",
    title="Bygning",
    default_api_url="http://localhost:8000/datasets/bygning/ogc_api",
    target_crs="EPSG:5972",
    geometry_type="MultiLineString",
    collections=_COLLECTIONS,
    required_fields={
        "bygning": _COMMON_REQUIRED_FIELDS,
        "bygning_omrade": _COMMON_REQUIRED_FIELDS,
    },
    identity_fields=("lokalid", "identifikasjon_navnerom"),
    geometry_types={
        "bygning": "MultiLineString",
        "bygning_omrade": "MultiPolygon",
    },
    merge_duplicate_multilinestrings=True,
)