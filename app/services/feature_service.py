from typing import AsyncGenerator, Awaitable, Callable, List, Tuple

import orjson
from psycopg import Connection

from app.db.fkb_ar5_dao import FKBAR5DAO
from app.models.fkb_felles import FKBFelles
from app.models.ogc import FeatureCollectionGeoJSON, FeatureGeoJSON
from app.postgis_backend import PostGISBackend


async def stream_feature_collection(
    collection_id: str, limit: int | None, after_id: str | None, conn: Connection
) -> AsyncGenerator[bytes, None]:
    # TODO: Implement other features, include type hinting
    generator = {
        "arealressursflate": FKBAR5DAO.get_all_arealressursflate,
    }[collection_id](conn, limit, after_id)
    yield b'{"type":"FeatureCollection","features":['
    first = True
    async for model, omrade_geojson in generator:
        if not first:
            yield b","
        first = False
        feature_bytes = (
            b'{"type":"Feature", "id":'
            + orjson.dumps(model.identifikasjon.lokal_id)
            + b', "geometry":'
            + omrade_geojson.encode()
            + b', "properties":'
            + orjson.dumps(model.model_dump())
            + b"}"
        )
        yield feature_bytes
    yield b"]}"


async def get_feature_geojson(
    collection_id: str, feature_id: str, conn: Connection
) -> dict:
    model, geometry = await {"arealressursflate": FKBAR5DAO.get_arealressursflate}[
        collection_id
    ](conn, feature_id)
    return {
        "type": "Feature",
        "id": model.identifikasjon.lokal_id,
        "geometry": orjson.loads(geometry),
        "properties": model.model_dump(),
    }


class FeatureService:
    def __init__(self, get_one, get_all, create):
        self.get_one: Callable[[str, Connection], Awaitable[Tuple[FKBFelles, dict]]] = (
            get_one
        )
        self.get_all: Callable[
            [Connection], Awaitable[List[Tuple[FKBFelles, dict]]]
        ] = get_all
        self.create = create

    def to_featuregeojson(self, featuredata: Tuple[FKBFelles, str]):
        return FeatureGeoJSON(
            id=featuredata[0].identifikasjon.lokal_id,
            geometry=featuredata[1],
            properties=featuredata[0],
        )

    async def get_feature(self, feature_id: str, conn: Connection) -> FeatureGeoJSON:
        properties, geometry = await self.get_one(feature_id, conn)
        return FeatureGeoJSON(
            id=properties.identifikasjon.lokal_id,
            geometry=geometry,
            properties=properties,
        )

    async def get_features(self, conn: Connection) -> FeatureCollectionGeoJSON:
        features = await self.get_all(conn)
        return FeatureCollectionGeoJSON(
            features=list(map(self.to_featuregeojson, features))
        )

    async def create_feature(self, feature: FeatureGeoJSON, conn: Connection):
        print(feature.geometry)
        created_id = await self.create(feature.properties, feature.geometry, conn)
        return created_id


def create_feature_service(collection_id: str):
    functions = {
        "jernbaneplattformkant": {
            "get_one": PostGISBackend.get_jernbaneplattformkant,
            "get_all": PostGISBackend.get_all_jernbaneplattformkant,
            "create": PostGISBackend.create_jernbaneplattformkant,
        },
        "spormidt": {
            "get_one": PostGISBackend.get_spormidt,
            "get_all": PostGISBackend.get_all_spormidt,
            "create": PostGISBackend.create_sportmidt,
        },
        "arealressursflate": {
            "get_one": FKBAR5DAO.get_arealressursflate,
            "get_all": FKBAR5DAO.get_all_arealressursflate,
            "create": FKBAR5DAO.create_arealressursflate,
        },
    }[collection_id]

    return FeatureService(**functions)
