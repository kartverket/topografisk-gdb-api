from typing import AsyncGenerator, Tuple

from psycopg import Connection, Cursor

import app.db.SQL as SQL  # noqa
from app.models.exceptions import FeatureNotFoundError
from app.models.fkb_ar5 import ArealressursFlate, ArealressursGrense
from app.models.ogc import FeatureGeoJSON

SELECT_MODEL_LOOKUP = {
    "arealressursgrense": {
        "select": SQL.AREALRESSURSGRENSE_SELECT,
        "model": ArealressursGrense,
    },
    "arealressursflate": {
        "select": SQL.AREALRESSURSFLATE_SELECT,
        "model": ArealressursFlate,
    },
}


class FKBAR5DAO:
    @staticmethod
    async def get_feature(
        conn: Connection,
        collection_id: str,
        feature_id: str,
    ) -> Tuple[ArealressursFlate, str]:
        """Fetch a single feature by collection and lokalid.

        Returns a tuple of (model, geometry) where geometry is a
        raw GeoJSON string of the main geometry column.
        Raises FeatureNotFoundError if no row matches.
        """
        result = await conn.execute(
            SELECT_MODEL_LOOKUP[collection_id]["select"] + SQL.WHERE_ID_EQUALS,
            params={"lokalid": feature_id},
        )
        row = await result.fetchone()

        if not row:
            raise FeatureNotFoundError(
                f"No element '{feature_id}' in collection {collection_id}."
            )

        return (
            SELECT_MODEL_LOOKUP[collection_id]["model"].from_db(row),
            row["main_geometry"],
        )

    @staticmethod
    async def get_feature_collection(
        conn: Connection,
        collection_id: str,
        limit: int,
        after_id: str | None = None,
    ) -> AsyncGenerator[Tuple[ArealressursFlate, str], None]:
        """Stream feature collection rows.

        Yields (model, geometry) tuples one at a time, keeping memory
        usage constant regardless of result size. Supports keyset pagination:
        pass after_id to start from the row after the given lokalid, ordered
        by lokalid. limit=None returns all matching rows.
        """
        cur: Cursor
        async with conn.cursor() as cur:
            await cur.execute(
                SELECT_MODEL_LOOKUP[collection_id]["select"] + SQL.AFTER_ID_LIMIT,
                params={"limit": limit, "after_id": after_id},
            )
            async for row in cur:
                yield (
                    SELECT_MODEL_LOOKUP[collection_id]["model"].from_db(row),
                    row["main_geometry"],
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
