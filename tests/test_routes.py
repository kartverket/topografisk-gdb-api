import datetime
import json
from unittest import TestCase
from unittest.mock import patch

from starlette.testclient import TestClient

from app.config import settings
from app.database_manager import get_db_conn
from app.main import app
from app.models.fkb_ar5 import ArealressursFlate
from app.models.fkb_felles import Identifikasjon

MOCK_OMRADE = '{"type":"Polygon","coordinates":[[[10.0,59.0],[10.1,59.0],[10.1,59.1],[10.0,59.0]]]}'
MOCK_POSISJON = '{"type":"Point","coordinates":[10.05,59.05]}'


def make_arealressursflate(lokal_id: str, posisjon: str | None) -> ArealressursFlate:
    return ArealressursFlate(
        identifikasjon=Identifikasjon(lokal_id=lokal_id, navnerom="test"),
        posisjon=json.loads(posisjon) if posisjon else None,
        oppdateringsdato=datetime.datetime(2024, 1, 1),
        datafangstdato=datetime.date(2024, 1, 1),
        arealtype="11",
        treslag="99",
        skogbonitet="98",
        grunnforhold="98",
        klassifiseringsmetode="sOrto",
    )


async def mock_get_all(conn, collection_id, bbox, datetime_query, limit, after_id=None):
    all_features = [
        (make_arealressursflate("id-1", MOCK_POSISJON), MOCK_OMRADE),
        (make_arealressursflate("id-2", None), MOCK_OMRADE),
    ]
    return all_features[:limit] if limit is not None else all_features


async def mock_db_conn():
    yield None


class TestArealressursflateRoute(TestCase):
    def setUp(self):
        app.dependency_overrides[get_db_conn] = mock_db_conn
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app, raise_server_exceptions=True)

    def test_get_items_returns_feature_collection(self):
        with patch("app.db.dao.get_features", side_effect=mock_get_all):
            response = self.client.get("/collections/arealressursflate/items?limit=10")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("FeatureCollection", body["type"])
        self.assertEqual(2, len(body["features"]))

    def test_feature_shape(self):
        with patch("app.db.dao.get_features", side_effect=mock_get_all):
            response = self.client.get("/collections/arealressursflate/items")

        feature = response.json()["features"][0]
        self.assertEqual("Feature", feature["type"])
        self.assertIn("id", feature)
        self.assertIn("geometry", feature)
        self.assertIn("properties", feature)
        self.assertEqual("id-1", feature["id"])

    def test_geometry_serialisation(self):
        with patch("app.db.dao.get_features", side_effect=mock_get_all):
            response = self.client.get("/collections/arealressursflate/items")

        features = response.json()["features"]
        self.assertEqual(json.loads(MOCK_OMRADE), features[0]["geometry"])
        self.assertEqual(
            json.loads(MOCK_POSISJON), features[0]["properties"]["posisjon"]
        )

    def test_null_posisjon_serialised_as_null(self):
        with patch("app.db.dao.get_features", side_effect=mock_get_all):
            response = self.client.get("/collections/arealressursflate/items")

        feature = response.json()["features"][1]
        self.assertIsNone(feature["properties"]["posisjon"])

    def test_limit_exceeds_max_page_size_is_clamped(self):
        with patch.dict(settings.__dict__, {"MAX_PAGE_SIZE": 1}):
            with patch("app.db.dao.get_features", side_effect=mock_get_all) as mock_dao:
                self.client.get("/collections/arealressursflate/items?limit=2")
        self.assertEqual(1, mock_dao.call_args.kwargs["limit"])

    def test_no_next_link_when_page_is_not_full(self):
        with patch.object(settings, "MAX_PAGE_SIZE", 10):
            with patch("app.db.dao.get_features", side_effect=mock_get_all):
                response = self.client.get(
                    "/collections/arealressursflate/items?limit=10"
                )

        body = response.json()
        rels = [link["rel"] for link in body.get("links", [])]
        self.assertNotIn("next", rels)


async def mock_get_one(conn, collection_id, feature_id):
    return (make_arealressursflate("id-1", MOCK_POSISJON), MOCK_OMRADE)


class TestArealressursflateItemRoute(TestCase):
    def setUp(self):
        app.dependency_overrides[get_db_conn] = mock_db_conn
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app, raise_server_exceptions=True)

    def test_get_item_returns_feature(self):
        with patch("app.db.dao.get_feature", side_effect=mock_get_one):
            response = self.client.get("/collections/arealressursflate/items/id-1")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("Feature", body["type"])
        self.assertEqual("id-1", body["id"])

    def test_item_geometry(self):
        with patch("app.db.dao.get_feature", side_effect=mock_get_one):
            response = self.client.get("/collections/arealressursflate/items/id-1")

        body = response.json()
        self.assertEqual(json.loads(MOCK_OMRADE), body["geometry"])
        self.assertEqual(json.loads(MOCK_POSISJON), body["properties"]["posisjon"])
