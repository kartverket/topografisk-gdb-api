from typing import List, Tuple

from psycopg import Connection

from app.models.fkb_ar5 import (
    ArealressursFlate,
    db_to_arealressurs_flate
)
from app.models.ogc import FeatureGeoJSON
from app.models.exceptions import FeatureNotFoundError

class FKBAR5DAO:
    @staticmethod
    async def get_arealressursflate(id: str, conn: Connection) -> Tuple[ArealressursFlate, dict]:
        result = await conn.execute(
            query=f"""
                SELECT *, ST_AsGeoJSON(omrade)::json AS omrade_geojson, ST_AsGeoJSON(posisjon)::json AS posisjon_geojson FROM fkb_ar5.arealressursflate 
                WHERE lokalid = %(id)s
            """,
            params={"id": id}
        )
        arealressurs_flate_row = await result.fetchone()

        if not arealressurs_flate_row:
            raise FeatureNotFoundError()

        return db_to_arealressurs_flate(arealressurs_flate_row), arealressurs_flate_row["omrade_geojson"]
    
    @staticmethod
    async def get_all_arealressursflate(conn: Connection) -> List[Tuple[ArealressursFlate, dict]]:
        result = await conn.execute(
            query=f"""
                SELECT *, ST_AsGeoJSON(omrade)::json AS omrade_geojson, ST_AsGeoJSON(posisjon)::json AS posisjon_geojson FROM fkb_ar5.arealressursflate
            """
        )
        arealressurs_flate_rows = await result.fetchall()

        return list(map(
            lambda row: (db_to_arealressurs_flate(row), row["omrade_geojson"]),
            arealressurs_flate_rows
        ))
    
    @staticmethod
    async def create_arealressursflate(feature: FeatureGeoJSON, conn: Connection):
        raise NotImplementedError()
