from __future__ import annotations

import json
from pathlib import Path

import pytest

from gcimport.importer import prepare_document
from gcimport.parsers.geojson_to_jsonfg import (
    ConversionError,
    convert_document,
    convert_file,
    normalize_crs,
)
from gcimport.profiles.bane import BANE_PROFILE
from gcimport.profiles.bygning import (
    _AREA_SOURCE_OBJTYPES as _BUILDING_AREA_SOURCE_OBJTYPES,
)
from gcimport.profiles.bygning import (
    _SOURCE_OBJTYPES,
    BYGNING_PROFILE,
)


def _source_feature(
    *,
    objtype: str = "Spormidt",
    lokalid: str = "bde1a163-2724-4c48-9101-04c839895292",
) -> dict:
    properties = {
        "objid": 31454,
        "objtype": objtype,
        "lokalid": lokalid,
        "identifikasjon_navnerom": "http://data.geonorge.no/SFKB/FKB-Bane/so",
        "identifikasjon_versjonid": "2024-12-16 13:56:44.104615000",
        "oppdateringsdato": "2026-02-26T09:04:27",
        "sluttdato": None,
        "datafangstdato": "2005-04-25T00:00:00",
        "verifiseringsdato": "2022-08-23T00:00:00",
        "registreringsversjon": None,
        "informasjon": None,
        "kvalitet_datafangstmetode": "fot",
        "kvalitet_noyaktighet": 19,
        "kvalitet_synbarhet": "0",
        "kvalitet_datafangstmetodehoyde": "fot",
        "kvalitet_noyaktighethoyde": None,
        "medium": "T",
        "eksternpeker": None,
    }
    if objtype.casefold() == "spormidt":
        properties["jernbanetype"] = "J"
        properties["hoydereferanse"] = "ukjent"
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [279754.06142351438757, 7041951.166005967184901, 5.86],
                [279761.890727702528238, 7041956.309099378995597, 5.54],
            ],
        },
    }


def _source_document(features: list[dict] | None = None) -> dict:
    return {
        "type": "FeatureCollection",
        "name": "bane",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::5973"},
        },
        "features": features if features is not None else [_source_feature()],
    }


def _building_source_feature(
    *,
    objtype: str = "BygningBru",
    lokalid: str = "579d9b68-cd85-473c-a4cb-31d6bfc94583",
) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "OBJECTID": 1,
            "objtype": objtype,
            "lokalid": lokalid,
            "datafangstdato": "2011-05-09T00:00:00Z",
            "oppdateringsdato": "2025-01-20T09:57:00Z",
            "navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
        },
        "geometry": {
            "type": "MultiLineString",
            "coordinates": [
                [
                    [522867.9097999996, 6857053.890000001, 302.19],
                    [522874.4998000003, 6857056.890000001, 301.94],
                    [522873.3398000002, 6857054.789999999, 301.81],
                    [522868.7898000004, 6857052.760000002, 301.85],
                    [522869.0697999997, 6857053.280000001, 301.85],
                    [522867.9097999996, 6857053.890000001, 302.19],
                ]
            ],
        },
    }


def _building_source_document(features: list[dict] | None = None) -> dict:
    return {
        "type": "FeatureCollection",
        "name": "fkb_bygning_grense",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::5972"},
        },
        "features": features if features is not None else [_building_source_feature()],
    }


def _building_area_source_feature(
    *,
    objtype: str = "AnnenBygning",
    lokalid: str = "8e17111d-7d7b-4720-88d1-af4eca45e2e4",
) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "OBJECTID": 1,
            "objtype": objtype,
            "lokalid": lokalid,
            "datafangstdato": "2026-03-03T00:00:00Z",
            "oppdateringsdato": "2026-03-04T00:31:16Z",
            "navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
        },
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [
                [
                    [
                        [529540.2541, 6853079.3009, 495.652],
                        [529544.7306, 6853080.6285, 495.652],
                        [529546.4499, 6853074.8313, 495.652],
                        [529541.9734, 6853073.5036, 495.652],
                        [529540.2541, 6853079.3009, 495.652],
                    ]
                ]
            ],
        },
    }


def _building_area_source_document(features: list[dict] | None = None) -> dict:
    return {
        "type": "FeatureCollection",
        "name": "fkb_bygning_omrade",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::5972"},
        },
        "features": features
        if features is not None
        else [_building_area_source_feature()],
    }


def _building_centerline_source_feature(
    *,
    objtype: str = "Hjelpelinje3D",
    lokalid: str = "0de78a64-886b-4272-9858-20f50d2ad6e0",
) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "OBJECTID": 1,
            "objtype": objtype,
            "lokalid": lokalid,
            "datafangstdato": "2011-05-09T00:00:00Z",
            "oppdateringsdato": "2026-02-28T00:31:01Z",
            "verifiseringsdato": "2025-07-11T00:00:00Z",
            "navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
            "tredniva": "2",
        },
        "geometry": {
            "type": "MultiLineString",
            "coordinates": [
                [
                    [517473.8998, 6846070.51, 450.46],
                    [517471.5698, 6846072.11, 450.56],
                ]
            ],
        },
    }


def _building_centerline_source_document(features: list[dict] | None = None) -> dict:
    return {
        "type": "FeatureCollection",
        "name": "fkb_bygning_senterlinje",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::5972"},
        },
        "features": features
        if features is not None
        else [_building_centerline_source_feature()],
    }


def _building_position_source_feature(
    *,
    objtype: str = "Bygning",
    lokalid: str = "ef033e10-97e2-4039-bc74-54de80a4e665",
) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "OBJECTID": 1,
            "objtype": objtype,
            "lokalid": lokalid,
            "datafangstdato": "2026-03-03T00:00:00Z",
            "oppdateringsdato": "2026-03-05T00:31:07Z",
            "navnerom": "http://data.geonorge.no/SFKB/FKB-Bygning/so",
            "medium": "X",
            "bygningsnummer": 301583667,
            "bygningstype": 241,
            "bygningsstatus": "IG",
            "kommunenummer": "3437",
        },
        "geometry": {
            "type": "Point",
            "coordinates": [529542.1498, 6853063.56, -99999.0],
        },
    }


def _building_position_source_document(features: list[dict] | None = None) -> dict:
    return {
        "type": "FeatureCollection",
        "name": "fkb_bygning_posisjon",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:EPSG::5972"},
        },
        "features": features
        if features is not None
        else [_building_position_source_feature()],
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("urn:ogc:def:crs:EPSG::5973", "EPSG:5973"),
        ("EPSG:4326", "EPSG:4326"),
        ("http://www.opengis.net/def/crs/EPSG/0/5973", "EPSG:5973"),
    ],
)
def test_normalize_crs(value: str, expected: str) -> None:
    assert normalize_crs(value) == expected


def test_convert_document_moves_geometry_to_place() -> None:
    converted = convert_document(_source_document())

    assert converted == {
        "type": "FeatureCollection",
        "coordRefSys": "EPSG:5973",
        "features": [
            {
                "type": "Feature",
                "featureType": "spormidt",
                "place": {
                    "type": "MultiLineString",
                    "coordinates": [
                        [
                            [279754.06142351438757, 7041951.166005967184901, 5.86],
                            [279761.890727702528238, 7041956.309099378995597, 5.54],
                        ]
                    ],
                },
                "properties": _source_feature()["properties"],
            }
        ],
    }
    assert "crs" not in converted
    assert "name" not in converted
    assert "geometry" not in converted["features"][0]


def test_convert_document_is_accepted_by_importer() -> None:
    converted = convert_document(
        _source_document(
            [
                _source_feature(),
                _source_feature(
                    objtype="Jernbaneplattformkant",
                    lokalid="11111111-1111-4111-8111-111111111111",
                ),
            ]
        )
    )

    prepared = prepare_document(converted, BANE_PROFILE)
    assert [item.collection for item in prepared] == [
        "spormidt",
        "jernbaneplattformkant",
    ]
    assert prepared[0].geojson["geometry"]["type"] == "MultiLineString"
    assert prepared[0].geojson["geometry"]["coordinates"][0][0][:2] == pytest.approx(
        [279754.06142351438757, 7041951.166005967184901]
    )


def test_convert_document_wraps_bane_linestring_as_multilinestring() -> None:
    converted = convert_document(_source_document())

    assert converted["features"][0]["place"]["type"] == "MultiLineString"
    assert converted["features"][0]["place"]["coordinates"] == [
        [
            [279754.06142351438757, 7041951.166005967184901, 5.86],
            [279761.890727702528238, 7041956.309099378995597, 5.54],
        ]
    ]


def test_convert_document_preserves_multipart_bane_as_multilinestring() -> None:
    feature = _source_feature()
    feature["geometry"] = {
        "type": "MultiLineString",
        "coordinates": [
            [
                [279754.06142351438757, 7041951.166005967184901, 5.86],
                [279761.890727702528238, 7041956.309099378995597, 5.54],
            ],
            [
                [279800.0, 7042000.0, 6.0],
                [279810.0, 7042010.0, 6.1],
            ],
        ],
    }

    converted = convert_document(_source_document([feature]))

    assert converted["features"][0]["place"]["type"] == "MultiLineString"
    assert len(converted["features"][0]["place"]["coordinates"]) == 2


def test_convert_document_preserves_bygning_multilinestring() -> None:
    converted = convert_document(
        _building_source_document(),
        profile=BYGNING_PROFILE,
    )

    assert converted["coordRefSys"] == "EPSG:5972"
    assert converted["features"][0]["featureType"] == "bygning"
    assert converted["features"][0]["place"]["type"] == "MultiLineString"
    assert converted["features"][0]["place"]["coordinates"] == [
        [
            [522867.9097999996, 6857053.890000001, 302.19],
            [522874.4998000003, 6857056.890000001, 301.94],
            [522873.3398000002, 6857054.789999999, 301.81],
            [522868.7898000004, 6857052.760000002, 301.85],
            [522869.0697999997, 6857053.280000001, 301.85],
            [522867.9097999996, 6857053.890000001, 302.19],
        ]
    ]


def test_convert_document_preserves_multipart_bygning_as_multilinestring() -> None:
    feature = _building_source_feature()
    feature["geometry"]["coordinates"].append(
        [
            [522880.0, 6857060.0, 302.0],
            [522881.0, 6857060.0, 302.0],
            [522881.0, 6857061.0, 302.0],
            [522880.0, 6857061.0, 302.0],
            [522880.0, 6857060.0, 302.0],
        ]
    )

    converted = convert_document(
        _building_source_document([feature]),
        profile=BYGNING_PROFILE,
    )

    assert converted["features"][0]["place"]["type"] == "MultiLineString"
    assert len(converted["features"][0]["place"]["coordinates"]) == 2


def test_convert_document_is_accepted_by_bygning_importer() -> None:
    converted = convert_document(
        _building_source_document(),
        profile=BYGNING_PROFILE,
    )

    prepared = prepare_document(converted, BYGNING_PROFILE)
    assert prepared[0].collection == "bygning"
    assert prepared[0].geojson["geometry"]["type"] == "MultiLineString"


def test_convert_document_preserves_bygning_omrade_multipolygon() -> None:
    converted = convert_document(
        _building_area_source_document(),
        profile=BYGNING_PROFILE,
    )

    assert converted["coordRefSys"] == "EPSG:5972"
    assert converted["features"][0]["featureType"] == "bygning_omrade"
    assert converted["features"][0]["place"]["type"] == "MultiPolygon"


def test_convert_document_is_accepted_by_bygning_omrade_importer() -> None:
    converted = convert_document(
        _building_area_source_document(),
        profile=BYGNING_PROFILE,
    )

    prepared = prepare_document(converted, BYGNING_PROFILE)
    assert prepared[0].collection == "bygning_omrade"
    assert prepared[0].geojson["geometry"]["type"] == "MultiPolygon"


@pytest.mark.parametrize("objtype", ("AnnenBygning", "Bygning", "Takoverbygg"))
def test_convert_document_supports_all_bygning_omrade_objtypes(objtype: str) -> None:
    converted = convert_document(
        _building_area_source_document(
            [_building_area_source_feature(objtype=objtype)]
        ),
        profile=BYGNING_PROFILE,
    )

    assert converted["features"][0]["featureType"] == "bygning_omrade"


def test_convert_document_routes_overlapping_bygning_objtype_by_geometry() -> None:
    converted = convert_document(
        _building_area_source_document(
            [_building_area_source_feature(objtype="Bygning")]
        ),
        profile=BYGNING_PROFILE,
    )

    assert converted["features"][0]["featureType"] == "bygning_omrade"


def test_convert_document_routes_hjelpelinje3d_to_bygning_senterlinje() -> None:
    converted = convert_document(
        _building_centerline_source_document(),
        profile=BYGNING_PROFILE,
    )

    assert converted["coordRefSys"] == "EPSG:5972"
    assert converted["features"][0]["featureType"] == "bygning_senterlinje"
    assert converted["features"][0]["place"]["type"] == "MultiLineString"


def test_convert_document_is_accepted_by_bygning_senterlinje_importer() -> None:
    converted = convert_document(
        _building_centerline_source_document(),
        profile=BYGNING_PROFILE,
    )

    prepared = prepare_document(converted, BYGNING_PROFILE)
    assert prepared[0].collection == "bygning_senterlinje"
    assert prepared[0].geojson["geometry"]["type"] == "MultiLineString"


def test_convert_document_routes_bygning_point_objtype_by_geometry() -> None:
    converted = convert_document(
        _building_position_source_document(),
        profile=BYGNING_PROFILE,
    )

    assert converted["coordRefSys"] == "EPSG:5972"
    assert converted["features"][0]["featureType"] == "bygning_posisjon"
    assert converted["features"][0]["place"] == {
        "type": "Point",
        "coordinates": [529542.1498, 6853063.56, -99999.0],
    }


def test_convert_document_is_accepted_by_bygning_position_importer() -> None:
    converted = convert_document(
        _building_position_source_document(),
        profile=BYGNING_PROFILE,
    )

    prepared = prepare_document(converted, BYGNING_PROFILE)
    assert prepared[0].collection == "bygning_posisjon"
    assert prepared[0].geojson["geometry"]["type"] == "Point"


def test_bygning_omrade_profile_tracks_scanned_objtypes() -> None:
    assert tuple(_BUILDING_AREA_SOURCE_OBJTYPES) == (
        "annenbygning",
        "bygning",
        "takoverbygg",
    )


@pytest.mark.parametrize(
    "objtype",
    tuple(
        name for name in _SOURCE_OBJTYPES if name not in {"bygning", "hjelpelinje3d"}
    ),
)
def test_convert_document_supports_all_bygning_objtypes(objtype: str) -> None:
    converted = convert_document(
        _building_source_document([_building_source_feature(objtype=objtype)]),
        profile=BYGNING_PROFILE,
    )

    assert converted["features"][0]["featureType"] == "bygning"


def test_convert_file_writes_jsonfg(tmp_path: Path) -> None:
    source = tmp_path / "bane.geojson"
    destination = tmp_path / "bane.jsonfg"
    source.write_text(json.dumps(_source_document()), encoding="utf-8")

    convert_file(source, destination)

    written = json.loads(destination.read_text(encoding="utf-8"))
    assert written["coordRefSys"] == "EPSG:5973"
    assert written["features"][0]["featureType"] == "spormidt"


def test_missing_crs_requires_override() -> None:
    document = _source_document()
    document.pop("crs")
    with pytest.raises(ConversionError, match="missing CRS"):
        convert_document(document)


def test_crs_override() -> None:
    document = _source_document()
    document.pop("crs")
    converted = convert_document(document, crs="EPSG:5973")
    assert converted["coordRefSys"] == "EPSG:5973"


def test_unknown_objtype() -> None:
    with pytest.raises(ConversionError, match=r"properties\.objtype must be one of"):
        convert_document(_source_document([_source_feature(objtype="Veg")]))


def test_wrong_profile_objtype_suggests_matching_profile() -> None:
    with pytest.raises(
        ConversionError,
        match=r"'BygningBru' belongs to the bygning profile",
    ):
        convert_document(
            _building_source_document(),
            profile=BANE_PROFILE,
        )


def test_wrong_profile_objtype_suggests_bygning_profile_for_area_objtype() -> None:
    feature = _building_area_source_feature()
    with pytest.raises(
        ConversionError,
        match=r"'AnnenBygning' belongs to the bygning profile",
    ):
        convert_document(
            _building_area_source_document([feature]),
            profile=BANE_PROFILE,
        )


def test_convert_document_applies_property_alias_fallbacks() -> None:
    feature = _source_feature()
    feature["properties"].pop("identifikasjon_navnerom")
    feature["properties"].pop("identifikasjon_versjonid")
    feature["properties"]["navnerom"] = "http://data.geonorge.no/SFKB/FKB-Bane/so"
    feature["properties"]["versjonid"] = "2026-02-25 09:10:42.653812000"
    feature["properties"].pop("kvalitet_datafangstmetode")
    feature["properties"].pop("kvalitet_noyaktighet")
    feature["properties"]["datafangstmetode"] = "fot"
    feature["properties"]["noyaktighet"] = 22

    converted = convert_document(_source_document([feature]))
    properties = converted["features"][0]["properties"]

    assert properties["identifikasjon_navnerom"] == (
        "http://data.geonorge.no/SFKB/FKB-Bane/so"
    )
    assert properties["identifikasjon_versjonid"] == "2026-02-25 09:10:42.653812000"
    assert properties["kvalitet_datafangstmetode"] == "fot"
    assert properties["kvalitet_noyaktighet"] == 22
