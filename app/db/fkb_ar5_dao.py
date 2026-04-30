from typing import AsyncGenerator, List, Tuple

from psycopg import Connection, Cursor

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
        lokal_id: str,
        conn: Connection,
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
            ArealressursFlate.from_db(
                arealressurs_flate_row, arealressurs_flate_row["posisjon_geojson"]
            ),
            arealressurs_flate_row["omrade_geojson"],
        )

    @staticmethod
    async def get_arealressursgrense(
        lokal_id: str,
        conn: Connection,
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
            ArealressursGrense.from_db(arealressurs_grense_row),
            arealressurs_grense_row["grense_geojson"],
        )

    @staticmethod
    async def get_all_arealressursflate(
        conn: Connection,
        bbox: List[float] | None = None,
        datetime_query: str | None = None,
        limit: int | None = None,
        after_id: str | None = None,
    ) -> AsyncGenerator[Tuple[ArealressursFlate, str], None]:
        """Stream arealressursflate rows using a named cursor (ar5_flater_stream).

        Yields (model, omrade_geojson) tuples one at a time, keeping memory
        usage constant regardless of result size. Supports keyset pagination:
        pass after_id to start from the row after the given lokalid, ordered
        by lokalid. limit=None returns all matching rows.
        """
        cur: Cursor
        async with conn.cursor(name="ar5_stream") as cur:
            query = AREALRESSURSFLATE_SELECT
            query += """
            WHERE (%(after_id)s::text IS NULL OR identifikasjon_lokal_id::text > %(after_id)s::text)
            """

            if bbox is not None:
                query += """
                AND ST_Intersects(ST_Transform(omrade::geometry, 4326), ST_MakeEnvelope(%(lower_left_x)s, %(lower_left_y)s, %(upper_right_x)s, %(upper_right_y)s, 4326))
                """

            query += """
            ORDER BY identifikasjon_lokal_id
            LIMIT %(limit)s
            """

            params = {
                "limit": limit,
                "after_id": after_id,
            }

            if bbox is not None:
                params["lower_left_x"] = bbox[0]
                params["lower_left_y"] = bbox[1]
                params["upper_right_x"] = bbox[2]
                params["upper_right_y"] = bbox[3]

            await cur.execute(
                query=query,
                params=params,
            )
            async for row in cur:
                yield (
                    ArealressursFlate.from_db(row, row["posisjon_geojson"]),
                    row["omrade_geojson"],
                )

    @staticmethod
    async def get_all_arealressursgrense(
        conn: Connection,
        bbox: List[float] | None = None,
        datetime_query: str | None = None,
        limit: int | None = None,
        after_id: str | None = None,
    ) -> AsyncGenerator[Tuple[ArealressursGrense, str], None]:
        """Stream arealressursgrense rows using a named cursor (ar5_grenser_stream).

        Yields (model, grense_geojson) tuples one at a time, keeping memory
        usage constant regardless of result size. Supports keyset pagination:
        pass after_id to start from the row after the given lokalid, ordered
        by lokalid. limit=None returns all matching rows.
        """
        async with conn.cursor(name="ar5_grenser_stream") as cur:
            query = AREALRESSURSGRENSE_SELECT
            query += """
            WHERE (%(after_id)s::text IS NULL OR identifikasjon_lokal_id::text > %(after_id)s::text)
            """

            if bbox is not None:
                query += """
                AND ST_Intersects(ST_Transform(grense::geometry, 4326), ST_MakeEnvelope(%(lower_left_x)s, %(lower_left_y)s, %(upper_right_x)s, %(upper_right_y)s, 4326))
                """

            query += """
            ORDER BY identifikasjon_lokal_id
            LIMIT %(limit)s
            """

            params = {
                "limit": limit,
                "after_id": after_id,
            }

            if bbox is not None:
                params["lower_left_x"] = bbox[0]
                params["lower_left_y"] = bbox[1]
                params["upper_right_x"] = bbox[2]
                params["upper_right_y"] = bbox[3]

            await cur.execute(
                query=query,
                params=params,
            )
            async for row in cur:
                yield (
                    ArealressursGrense.from_db(row),
                    row["grense_geojson"],
                )

    @staticmethod
    async def create_arealressursflate(feature: FeatureGeoJSON, conn: Connection):
        raise NotImplementedError()

    @staticmethod
    async def create_arealressursgrense(feature: FeatureGeoJSON, conn: Connection):
        raise NotImplementedError()

    @staticmethod
    async def patch_arealressursflate(feature: FeatureGeoJSON, conn: Connection):
        await conn.execute(
            """UPDATE topo_ar5ngis.face_attributes 
            SET
            datafangstdato=%(datafangstdato)s, 
            informasjon=%(informasjon)s, 
            verifiseringsdato=%(verifiseringsdato)s, 
            klassifiseringsmetode=%(klassifiseringsmetode)s, 
            oppdateringsdato=%(oppdateringsdato)s, 
            arealtype=%(arealtype)s, 
            treslag=%(treslag)s, 
            skogbonitet=%(skogbonitet)s, 
            grunnforhold=%(grunnforhold)s,
            registreringsversjon=%(registreringsversjon)s
            WHERE identifikasjon_lokal_id::text = %(lokalid)s; 
            """,
            params={
                "lokalid": feature.properties["identifikasjon"]["lokal_id"],
                "datafangstdato": feature.properties["datafangstdato"],
                "informasjon": feature.properties["informasjon"],
                "verifiseringsdato": feature.properties["verifiseringsdato"],
                "klassifiseringsmetode": feature.properties[
                    "klassifiseringsmetode"
                ].value,
                "oppdateringsdato": feature.properties["oppdateringsdato"],
                "arealtype": feature.properties["arealtype"].value,
                "treslag": feature.properties["treslag"].value,
                "skogbonitet": feature.properties["skogbonitet"].value,
                "grunnforhold": feature.properties["grunnforhold"].value,
                "registreringsversjon": feature.properties["registreringsversjon"],
            },
        )
