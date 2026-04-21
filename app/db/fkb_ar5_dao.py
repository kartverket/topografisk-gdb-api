from typing import AsyncGenerator, Tuple

from psycopg import Connection

from app.models.exceptions import FeatureNotFoundError
from app.models.fkb_ar5 import ArealressursFlate, db_to_arealressurs_flate
from app.models.ogc import FeatureGeoJSON


class FKBAR5DAO:
    @staticmethod
    async def get_arealressursflate(
        lokal_id: str, conn: Connection
    ) -> Tuple[ArealressursFlate, str]:
        result = await conn.execute(
            """
            SELECT 
                *,
                ST_AsGeoJSON(omrade)::text AS omrade_geojson,
                ST_AsGeoJSON(posisjon)::text AS posisjon_geojson 
            FROM fkb_ar5.arealressursflate 
            WHERE lokalid = %(lokalid)s
            """,
            params={"lokalid": lokal_id},
        )
        arealressurs_flate_row = await result.fetchone()

        if not arealressurs_flate_row:
            raise FeatureNotFoundError()

        return (
            db_to_arealressurs_flate(arealressurs_flate_row),
            arealressurs_flate_row["omrade_geojson"],
        )

    @staticmethod
    async def get_all_arealressursflate(
        conn: Connection, limit: int | None = None, after_id: str | None = None
    ) -> AsyncGenerator[Tuple[ArealressursFlate, str], None]:
        async with conn.cursor(name="ar5_stream") as cur:
            await cur.execute(
                """
                SELECT 
                    *, 
                    ST_AsGeoJSON(omrade)::text AS omrade_geojson, 
                    ST_AsGeoJSON(posisjon)::text AS posisjon_geojson 
                FROM fkb_ar5.arealressursflate
                WHERE (%(after_id)s IS NULL OR lokalid > %(after_id)s)
                ORDER BY lokalid
                LIMIT %(limit)s
                """,
                params={"limit": limit, "after_id": after_id},
            )
            async for row in cur:
                yield (db_to_arealressurs_flate(row), row["omrade_geojson"])

    @staticmethod
    async def create_arealressursflate(feature: FeatureGeoJSON, conn: Connection):
        raise NotImplementedError()
