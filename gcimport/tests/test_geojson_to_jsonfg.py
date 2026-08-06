from __future__ import annotations

import json
from pathlib import Path

import pytest

from gcimport.geojson_to_jsonfg import (
    ConversionError,
    convert_document,
    convert_file,
    normalize_crs,
)
from gcimport.importer import prepare_document
from gcimport.profiles.bane import BANE_PROFILE


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
                    "type": "LineString",
                    "coordinates": [
                        [279754.06142351438757, 7041951.166005967184901, 5.86],
                        [279761.890727702528238, 7041956.309099378995597, 5.54],
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
    assert prepared[0].geojson["geometry"]["coordinates"][0][:2] == pytest.approx(
        [279754.06142351438757, 7041951.166005967184901]
    )


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
