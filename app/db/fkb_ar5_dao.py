from typing import AsyncGenerator, Tuple

from psycopg import Connection

from app.models.exceptions import FeatureNotFoundError
from app.models.fkb_ar5 import ArealressursFlate, db_to_arealressurs_flate
from app.models.ogc import FeatureGeoJSON


class FKBAR5DAO:
    @staticmethod
    async def get_arealressursflate(
        conn: Connection,
        lokal_id: str,
    ) -> Tuple[ArealressursFlate, str]:
        """Fetch a single arealressursflate by lokalid.

        Returns a tuple of (model, omrade_geojson) where omrade_geojson is a
        raw GeoJSON string. Raises FeatureNotFoundError if no row matches.
        """
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
            raise FeatureNotFoundError(
                f"No element '{lokal_id}' in collection arealressursflate."
            )

        return (
            db_to_arealressurs_flate(
                arealressurs_flate_row, arealressurs_flate_row["posisjon_geojson"]
            ),
            arealressurs_flate_row["omrade_geojson"],
        )

    @staticmethod
    async def get_all_arealressursflate(
        conn: Connection, limit: int | None = None, after_id: str | None = None
    ) -> AsyncGenerator[Tuple[ArealressursFlate, str], None]:
        """Stream arealressursflate rows using a named cursor (ar5_stream).

        Yields (model, omrade_geojson) tuples one at a time, keeping memory
        usage constant regardless of result size. Supports keyset pagination:
        pass after_id to start from the row after the given lokalid, ordered
        by lokalid. limit=None returns all matching rows.
        """
        async with conn.cursor(name="ar5_stream") as cur:
            await cur.execute(
                """
                SELECT 
                    *, 
                    ST_AsGeoJSON(omrade)::text AS omrade_geojson, 
                    ST_AsGeoJSON(posisjon)::text AS posisjon_geojson 
                FROM fkb_ar5.arealressursflate
                WHERE (%(after_id)s::text IS NULL OR lokalid > %(after_id)s::text)
                ORDER BY lokalid
                LIMIT %(limit)s
                """,
                params={"limit": limit, "after_id": after_id},
            )
            async for row in cur:
                yield (
                    db_to_arealressurs_flate(row, row["posisjon_geojson"]),
                    row["omrade_geojson"],
                )

    @staticmethod
    async def create_arealressursflate(feature: FeatureGeoJSON, conn: Connection):
        raise NotImplementedError()
