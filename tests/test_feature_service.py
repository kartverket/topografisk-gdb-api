import json
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from app.models.fkb_bane import (
    Datafangstmetode,
    Hoydereferanse,
    Identifikasjon,
    JernbaneplattformkantProperties,
    Jernbanetype,
    Medium,
    Posisjonskvalitet,
    SpormidtProperties,
)
from app.models.ogc import FeatureCollectionGeoJSON, FeatureGeoJSON
from app.postgis_backend import PostGISBackend
from app.services.feature_service import get_feature_geojson, stream_feature_collection


def get_test_geometries():
    return [
        json.dumps(
            {
                "type": "LineString",
                "coordinates": [
                    [267779.71748773, 7038554.33060874, 164.78],
                    [267791.908078314, 7038540.100148616, 164.36],
                    [267801.261600452, 7038529.261796265, 163.77],
                ],
            }
        ).encode("utf-8"),
        json.dumps(
            {
                "type": "LineString",
                "coordinates": [
                    [267252.60920833, 7039103.461850385, 191.2],
                    [267248.841590744, 7039100.479157028, 191.03],
                    [267251.738305063, 7039096.438212778, 190.86],
                ],
            }
        ).encode("utf-8"),
    ]


class TestJernbaneplattformkantService(IsolatedAsyncioTestCase):
    @staticmethod
    def get_test_properties():
        return [
            JernbaneplattformkantProperties(
                identifikasjon=Identifikasjon(
                    lokal_id="test_id_1", navnerom="navnerom_1", versjon_id="0.0.1"
                ),
                oppdateringsdato="2026-01-02",
                datafangstdato="2026-01-01",
                kvalitet=Posisjonskvalitet(datafangstmetode=Datafangstmetode["dig"]),
                medium=Medium["T"],
            ),
            JernbaneplattformkantProperties(
                identifikasjon=Identifikasjon(
                    lokal_id="test_id_2", navnerom="navnerom_1", versjon_id="0.0.1"
                ),
                oppdateringsdato="2026-02-02",
                datafangstdato="2026-02-01",
                kvalitet=Posisjonskvalitet(datafangstmetode=Datafangstmetode["dig"]),
                medium=Medium["T"],
            ),
        ]

    async def test_get_feature(self):
        properties = TestJernbaneplattformkantService.get_test_properties()
        geometries = get_test_geometries()

        PostGISBackend.get_jernbaneplattformkant = AsyncMock(
            return_value=(properties[0], geometries[0])
        )
        connection = None  # Not necessary since get_jernbaneplattformkant is mocked

        actual_feature: FeatureGeoJSON = await get_feature_geojson(
            "jernbaneplattformkant", "test_id_1", connection
        )

        self.assertEqual("test_id_1", actual_feature.id)
        self.assertEqual("LineString", actual_feature.geometry.type)

    # async def test_get_features(self):
    #     properties = self.get_test_properties()
    #     geometries = get_test_geometries()

    #     expected = [[properties[0], geometries[0]], [properties[1], geometries[1]]]

    #     PostGISBackend.get_all_jernbaneplattformkant = AsyncMock(return_value=expected)
    #     connection = None  # Not necessary since get_jernbaneplattformkant is mocked

    #     feature_collection: FeatureCollectionGeoJSON = stream_feature_collection(
    #         collection_id="jernbaneplattformkant",
    #         limit=None,
    #         after_id=None,
    #         conn=connection,
    #         request_url="dummy.url",
    #     )

    #     self.assertEqual("test_id_1", feature_collection.features[0].id)
    #     self.assertEqual("test_id_2", feature_collection.features[1].id)
    #     self.assertEqual("LineString", feature_collection.features[0].geometry.type)
    #     self.assertEqual("LineString", feature_collection.features[1].geometry.type)


class TestSpormidtService(IsolatedAsyncioTestCase):
    @staticmethod
    def get_test_properties():
        return [
            SpormidtProperties(
                identifikasjon=Identifikasjon(
                    lokal_id="test_id_1", navnerom="navnerom_1", versjon_id="0.0.1"
                ),
                oppdateringsdato="2026-01-02",
                datafangstdato="2026-01-01",
                kvalitet=Posisjonskvalitet(datafangstmetode=Datafangstmetode["dig"]),
                medium=Medium["T"],
                jernbanetype=Jernbanetype["J"],
                hoydereferanse=Hoydereferanse["fot"],
            ),
            SpormidtProperties(
                identifikasjon=Identifikasjon(
                    lokal_id="test_id_2", navnerom="navnerom_1", versjon_id="0.0.1"
                ),
                oppdateringsdato="2026-02-02",
                datafangstdato="2026-02-01",
                kvalitet=Posisjonskvalitet(datafangstmetode=Datafangstmetode["dig"]),
                medium=Medium["T"],
                jernbanetype=Jernbanetype["J"],
                hoydereferanse=Hoydereferanse["fot"],
            ),
        ]

    async def test_get_feature(self):
        properties = TestSpormidtService.get_test_properties()
        geometries = get_test_geometries()

        PostGISBackend.get_spormidt = AsyncMock(
            return_value=(properties[0], geometries[0])
        )
        connection = None  # Not necessary since get_spormidt is mocked

        actual_feature: FeatureGeoJSON = await get_feature_geojson(
            "spormidt", "test_id_1", connection
        )

        self.assertEqual("test_id_1", actual_feature.id)
        self.assertEqual("LineString", actual_feature.geometry.type)

    # async def test_get_features(self):
    #     properties = self.get_test_properties()
    #     geometries = get_test_geometries()

    #     expected = [[properties[0], geometries[0]], [properties[1], geometries[1]]]

    #     PostGISBackend.get_all_spormidt = AsyncMock(return_value=expected)
    #     connection = None  # Not necessary since get_spormidt is mocked

    #     feature_collection: FeatureCollectionGeoJSON = stream_feature_collection(
    #         collection_id="spormidt",
    #         limit=None,
    #         after_id=None,
    #         conn=connection,
    #         request_url="dummy.url",
    #     )

    #     self.assertEqual("test_id_1", feature_collection.features[0].id)
    #     self.assertEqual("test_id_2", feature_collection.features[1].id)
    #     self.assertEqual("LineString", feature_collection.features[0].geometry.type)
    #     self.assertEqual("LineString", feature_collection.features[1].geometry.type)
