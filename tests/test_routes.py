import datetime
import json
from unittest import TestCase
from unittest.mock import patch

from starlette.testclient import TestClient

from app.config import settings
from app.database_manager import get_db_conn
from app.db.fkb_ar5_dao import FKBAR5DAO
from app.main import app
from app.models.fkb_ar5 import ArealressursFlate
from app.models.fkb_felles import Identifikasjon

FAKE_OMRADE = '{"type":"Polygon","coordinates":[[[10.0,59.0],[10.1,59.0],[10.1,59.1],[10.0,59.0]]]}'
FAKE_POSISJON = '{"type":"Point","coordinates":[10.05,59.05]}'


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


async def fake_get_all(conn, limit, after_id, target_srid=4326):
    yield (make_arealressursflate("id-1", FAKE_POSISJON), FAKE_OMRADE)
    yield (make_arealressursflate("id-2", None), FAKE_OMRADE)


async def mock_db_conn():
    yield None


class TestArealressursflateRoute(TestCase):
    def setUp(self):
        app.dependency_overrides[get_db_conn] = mock_db_conn
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app, raise_server_exceptions=True)

    def test_get_items_returns_feature_collection(self):
        with patch.object(
            FKBAR5DAO, "get_all_arealressursflate", side_effect=fake_get_all
        ):
            response = self.client.get("/collections/arealressursflate/items?limit=10")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("FeatureCollection", body["type"])
        self.assertEqual(2, len(body["features"]))

    def test_feature_shape(self):
        with patch.object(
            FKBAR5DAO, "get_all_arealressursflate", side_effect=fake_get_all
        ):
            response = self.client.get("/collections/arealressursflate/items")

        feature = response.json()["features"][0]
        self.assertEqual("Feature", feature["type"])
        self.assertIn("id", feature)
        self.assertIn("geometry", feature)
        self.assertIn("properties", feature)
        self.assertEqual("id-1", feature["id"])

    def test_geometry_serialisation(self):
        with patch.object(
            FKBAR5DAO, "get_all_arealressursflate", side_effect=fake_get_all
        ):
            response = self.client.get("/collections/arealressursflate/items")

        features = response.json()["features"]
        self.assertEqual(json.loads(FAKE_OMRADE), features[0]["geometry"])
        self.assertEqual(
            json.loads(FAKE_POSISJON), features[0]["properties"]["posisjon"]
        )

    def test_null_posisjon_serialised_as_null(self):
        with patch.object(
            FKBAR5DAO, "get_all_arealressursflate", side_effect=fake_get_all
        ):
            response = self.client.get("/collections/arealressursflate/items")

        feature = response.json()["features"][1]
        self.assertIsNone(feature["properties"]["posisjon"])

    def test_limit_exceeds_max_page_size_returns_400(self):
        with patch.object(settings, "MAX_PAGE_SIZE", 1):
            response = self.client.get("/collections/arealressursflate/items?limit=2")

        self.assertEqual(400, response.status_code)

    def test_next_link_present_when_page_is_full(self):
        with patch.object(settings, "MAX_PAGE_SIZE", 2):
            with patch.object(
                FKBAR5DAO, "get_all_arealressursflate", side_effect=fake_get_all
            ):
                response = self.client.get("/collections/arealressursflate/items?limit=2")

        body = response.json()
        links = {link["rel"]: link["href"] for link in body.get("links", [])}
        self.assertIn("next", links)
        self.assertIn("after_id=id-2", links["next"])

    def test_no_next_link_when_page_is_not_full(self):
        with patch.object(settings, "MAX_PAGE_SIZE", 10):
            with patch.object(
                FKBAR5DAO, "get_all_arealressursflate", side_effect=fake_get_all
            ):
                response = self.client.get("/collections/arealressursflate/items?limit=10")

        body = response.json()
        rels = [link["rel"] for link in body.get("links", [])]
        self.assertNotIn("next", rels)


async def fake_get_one(lokal_id, conn, target_srid=4326):
    return (make_arealressursflate("id-1", FAKE_POSISJON), FAKE_OMRADE)


class TestArealressursflateItemRoute(TestCase):
    def setUp(self):
        app.dependency_overrides[get_db_conn] = mock_db_conn
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app, raise_server_exceptions=True)

    def test_get_item_returns_feature(self):
        with patch.object(
            FKBAR5DAO, "get_arealressursflate", side_effect=fake_get_one
        ):
            response = self.client.get("/collections/arealressursflate/items/id-1")

        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual("Feature", body["type"])
        self.assertEqual("id-1", body["id"])

    def test_item_geometry(self):
        with patch.object(
            FKBAR5DAO, "get_arealressursflate", side_effect=fake_get_one
        ):
            response = self.client.get("/collections/arealressursflate/items/id-1")

        body = response.json()
        self.assertEqual(json.loads(FAKE_OMRADE), body["geometry"])
        self.assertEqual(json.loads(FAKE_POSISJON), body["properties"]["posisjon"])
