import orjson
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

from pydantic import BaseModel

from app.models.fkb_felles import Identifikasjon
from app.services.feature_service import get_feature_collection, get_feature_geojson

MOCK_GEOMETRY = '{"type":"Polygon","coordinates":[[[10.0,59.0],[10.1,59.0],[10.1,59.1],[10.0,59.0]]]}'


class GenericFeature(BaseModel):
    identifikasjon: Identifikasjon
    label: str = "test"


def make_generic_feature(lokal_id: str) -> GenericFeature:
    return GenericFeature(
        identifikasjon=Identifikasjon(lokal_id=lokal_id, navnerom="test")
    )


async def mock_get_all(conn, collection_id, limit, after_id=None):
    return [
        (make_generic_feature("id-1"), MOCK_GEOMETRY),
        (make_generic_feature("id-2"), MOCK_GEOMETRY),
    ]


async def mock_get_one(conn, collection_id, feature_id):
    return (make_generic_feature("id-1"), MOCK_GEOMETRY)


class TestGetFeatureGeoJSON(IsolatedAsyncioTestCase):
    async def test_returns_feature_geojson(self):
        with patch("app.db.dao.get_feature", side_effect=mock_get_one):
            result = await get_feature_geojson("arealressursflate", "id-1", None)

        feature = orjson.loads(result)
        self.assertEqual("Feature", feature["type"])
        self.assertEqual("id-1", feature["id"])
        self.assertEqual("Polygon", feature["geometry"]["type"])
        self.assertIn("label", feature["properties"])


class TestGetFeatureCollection(IsolatedAsyncioTestCase):
    async def _collect(self, **kwargs) -> dict:
        with patch("app.db.dao.get_feature_collection", side_effect=mock_get_all):
            return orjson.loads(await get_feature_collection(**kwargs))

    async def test_returns_feature_collection(self):
        body = await self._collect(
            collection_id="arealressursflate",
            limit=10,
            after_id=None,
            conn=None,
            request_url="http://test/collections/arealressursflate/items?limit=10",
        )
        self.assertEqual("FeatureCollection", body["type"])
        self.assertEqual(2, len(body["features"]))

    async def test_feature_shape(self):
        body = await self._collect(
            collection_id="arealressursflate",
            limit=10,
            after_id=None,
            conn=None,
            request_url="http://test/collections/arealressursflate/items?limit=10",
        )
        feature = body["features"][0]
        self.assertEqual("Feature", feature["type"])
        self.assertEqual("id-1", feature["id"])
        self.assertIn("geometry", feature)
        self.assertIn("label", feature["properties"])

    async def test_number_returned(self):
        body = await self._collect(
            collection_id="arealressursflate",
            limit=10,
            after_id=None,
            conn=None,
            request_url="http://test/collections/arealressursflate/items?limit=10",
        )
        self.assertEqual(2, body["numberReturned"])

    async def test_next_link_present_when_page_full(self):
        body = await self._collect(
            collection_id="arealressursflate",
            limit=2,
            after_id=None,
            conn=None,
            request_url="http://test/collections/arealressursflate/items?limit=2",
        )
        links = {link["rel"]: link["href"] for link in body.get("links", [])}
        self.assertIn("next", links)
        self.assertIn("after_id=id-2", links["next"])

    async def test_no_next_link_when_page_not_full(self):
        body = await self._collect(
            collection_id="arealressursflate",
            limit=10,
            after_id=None,
            conn=None,
            request_url="http://test/collections/arealressursflate/items?limit=10",
        )
        rels = [link["rel"] for link in body.get("links", [])]
        self.assertNotIn("next", rels)
