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

_CENTERLINE_SOURCE_OBJTYPES = ("hjelpelinje3d",)

_AREA_SOURCE_OBJTYPES = (
    "annenbygning",
    "bygning",
    "takoverbygg",
)

_POINT_SOURCE_OBJTYPES = ("bygning",)

_SOURCE_OBJTYPES = _LINE_SOURCE_OBJTYPES + _CENTERLINE_SOURCE_OBJTYPES

_COMMON_REQUIRED_FIELDS = frozenset(
    {
        "lokalid",
        "identifikasjon_navnerom",
        "oppdateringsdato",
        "datafangstdato",
    }
)

_COLLECTIONS: dict[str, str | tuple[str, ...]] = {
    **dict.fromkeys(_LINE_SOURCE_OBJTYPES, "bygning"),
    **dict.fromkeys(_CENTERLINE_SOURCE_OBJTYPES, "bygning_senterlinje"),
    **dict.fromkeys(_AREA_SOURCE_OBJTYPES, "bygning_omrade"),
    **dict.fromkeys(_POINT_SOURCE_OBJTYPES, "bygning_posisjon"),
    "bygning": ("bygning", "bygning_omrade", "bygning_posisjon"),
}

BYGNING_PROFILE = ImportProfile(
    name="bygning",
    title="Bygning",
    dataset_api_path="/datasets/bygning/ogc_api",
    target_crs="EPSG:5972",
    geometry_type="MultiLineString",
    collections=_COLLECTIONS,
    required_fields={
        "bygning": _COMMON_REQUIRED_FIELDS,
        "bygning_senterlinje": _COMMON_REQUIRED_FIELDS,
        "bygning_omrade": _COMMON_REQUIRED_FIELDS,
        "bygning_posisjon": _COMMON_REQUIRED_FIELDS,
    },
    identity_fields=("lokalid", "identifikasjon_navnerom"),
    geometry_types={
        "bygning": "MultiLineString",
        "bygning_senterlinje": "MultiLineString",
        "bygning_omrade": "MultiPolygon",
        "bygning_posisjon": "Point",
    },
    merge_duplicate_multilinestrings=True,
)
