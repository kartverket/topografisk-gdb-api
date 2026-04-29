from typing import AsyncGenerator, Tuple

from psycopg import Connection

from app.models.exceptions import FeatureNotFoundError
from app.models.fkb_ar5 import ArealressursFlate, ArealressursGrense
from app.models.ogc import FeatureGeoJSON

# Need to unpack for now because of postgis topology
# TODO: Fix in declarative setup later if possible
AREALRESSURSFLATE_SELECT = """
SELECT
    -- identity
    identifikasjon_lokal_id::text         AS lokalid,
    identifikasjon_versjon_id::text       AS identifikasjon_versjonid,
    identifikasjon_navnerom,

    -- dates
    datafangstdato,
    verifiseringsdato,
    oppdateringsdato,

    -- text fields
    klassifiseringsmetode,
    informasjon,
    opphav,
    registreringsversjon::text,

    -- enum codes
    arealtype::text,
    treslag::text,
    skogbonitet::text,
    grunnforhold::text,

    -- geometry
    ST_AsGeoJSON(ST_Transform(omrade::geometry, 4326))::text  AS omrade_geojson,
    ST_AsGeoJSON(geometry_properties_position)::text          AS posisjon_geojson

FROM topo_ar5ngis.face_attributes
"""


AREALRESSURSGRENSE_SELECT = """
SELECT
    -- identity
    identifikasjon_lokal_id::text   AS lokalid,
    identifikasjon_versjon_id::text AS identifikasjon_versjonid,
    identifikasjon_navnerom,

    -- dates
    datafangstdato,
    verifiseringsdato,
    oppdateringsdato,

    -- text fields
    opphav,
    registreringsversjon::text,

    -- enum codes
    avgrensing_type::text,
    
    -- composite
    (topo_ar5ngis.edge_attributes.kvalitet).datafangstmetode::text      AS datafangstmetode,
    (topo_ar5ngis.edge_attributes.kvalitet).noyaktighet::integer        AS noyaktighet,
    (topo_ar5ngis.edge_attributes.kvalitet).synbarhet::integer          AS synbarhet,

    -- geometry
    ST_AsGeoJSON(ST_Transform(grense::geometry, 4326))::text  AS grense_geojson

FROM topo_ar5ngis.edge_attributes
"""


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
            AREALRESSURSFLATE_SELECT
            + " WHERE identifikasjon_lokal_id::text = %(lokalid)s",
            params={"lokalid": lokal_id},
        )
        arealressurs_flate_row = await result.fetchone()

        if not arealressurs_flate_row:
            raise FeatureNotFoundError(
                f"No element '{lokal_id}' in collection arealressursflate."
            )

        return (
            ArealressursFlate.db_to_arealressurs_flate(
                arealressurs_flate_row, arealressurs_flate_row["posisjon_geojson"]
            ),
            arealressurs_flate_row["omrade_geojson"],
        )


    @staticmethod
    async def get_arealressursgrense(
        conn: Connection,
        lokal_id: str,
    ) -> Tuple[ArealressursGrense, str]:
        """Fetch a single arealressursgrense by lokalid.

        Returns a tuple of (model, grense_geojson) where grense_geojson is a
        raw GeoJSON string. Raises FeatureNotFoundError if no row matches.
        """
        result = await conn.execute(
            AREALRESSURSGRENSE_SELECT
            + " WHERE identifikasjon_lokal_id::text = %(lokalid)s",
            params={"lokalid": lokal_id},
        )
        arealressurs_grense_row = await result.fetchone()

        if not arealressurs_grense_row:
            raise FeatureNotFoundError(
                f"No element '{lokal_id}' in collection arealressursgrense."
            )

        return (
            ArealressursGrense.db_to_arealressurs_grense(
                arealressurs_grense_row
            ),
            arealressurs_grense_row["grense_geojson"],
        )


    @staticmethod
    async def get_all_arealressursflate(
        conn: Connection, limit: int | None = None, after_id: str | None = None
    ) -> AsyncGenerator[Tuple[ArealressursFlate, str], None]:
        """Stream arealressursflate rows using a named cursor (ar5_flater_stream).

        Yields (model, omrade_geojson) tuples one at a time, keeping memory
        usage constant regardless of result size. Supports keyset pagination:
        pass after_id to start from the row after the given lokalid, ordered
        by lokalid. limit=None returns all matching rows.
        """
        async with conn.cursor(name="ar5_flater_stream") as cur:
            await cur.execute(
                AREALRESSURSFLATE_SELECT
                + """
                WHERE (%(after_id)s::text IS NULL OR identifikasjon_lokal_id::text > %(after_id)s::text)
                ORDER BY identifikasjon_lokal_id
                LIMIT %(limit)s
                """,
                params={"limit": limit, "after_id": after_id},
            )
            async for row in cur:
                yield (
                    ArealressursFlate.db_to_arealressurs_flate(row, row["posisjon_geojson"]),
                    row["omrade_geojson"],
                )


    @staticmethod
    async def get_all_arealressursgrense(
        conn: Connection, limit: int | None = None, after_id: str | None = None
    ) -> AsyncGenerator[Tuple[ArealressursGrense, str], None]:
        """Stream arealressursgrense rows using a named cursor (ar5_grenser_stream).

        Yields (model, grense_geojson) tuples one at a time, keeping memory
        usage constant regardless of result size. Supports keyset pagination:
        pass after_id to start from the row after the given lokalid, ordered
        by lokalid. limit=None returns all matching rows.
        """
        async with conn.cursor(name="ar5_grenser_stream") as cur:
            await cur.execute(
                AREALRESSURSGRENSE_SELECT
                + """
                WHERE (%(after_id)s::text IS NULL OR identifikasjon_lokal_id::text > %(after_id)s::text)
                ORDER BY identifikasjon_lokal_id
                LIMIT %(limit)s
                """,
                params={"limit": limit, "after_id": after_id},
            )
            async for row in cur:
                yield (
                    ArealressursGrense.db_to_arealressurs_grense(row),
                    row["grense_geojson"],
                )


    @staticmethod
    async def create_arealressursflate(feature: FeatureGeoJSON, conn: Connection):
        raise NotImplementedError()

    @staticmethod
    async def create_arealressursgrense(feature: FeatureGeoJSON, conn: Connection):
        raise NotImplementedError()