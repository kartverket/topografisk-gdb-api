"""
Data access layer. Executes SQL and maps rows to domain models
via SQL_MODEL_LOOKUP.

Temporary: SQL is hard-coded per collection until replaced by a
declarative schema-driven setup.

To add a collection or operation, write proper SQL and attach it
to SQL_MODEL_LOOKUP.
"""

from typing import Tuple

from psycopg import Connection

import app.db.ar5_sql as ar5_sql  # noqa
import app.db.jernbane_sql as jernbane_sql  # noqa
from app.models.exceptions import FeatureNotFoundError
from app.models.fkb_ar5 import ArealressursFlate, ArealressursGrense
from app.models.fkb_bane import JernbaneplattformkantProperties, SpormidtProperties
from app.models.ogc import FeatureGeoJSON

SQL_MODEL_LOOKUP = {
    "arealressursgrense": {
        "select": ar5_sql.AREALRESSURSGRENSE_SELECT,
        "model": ArealressursGrense,
        "sql_queries": ar5_sql,
    },
    "arealressursflate": {
        "select": ar5_sql.AREALRESSURSFLATE_SELECT,
        "model": ArealressursFlate,
        "sql_queries": ar5_sql,
    },
    "jernbaneplattformkant": {
        "select": jernbane_sql.JERNBANEPLATTFORM_SELECT,
        "create": jernbane_sql.JERNBANEPLATTFORM_CREATE,
        "model": JernbaneplattformkantProperties,
        "sql_queries": jernbane_sql,
    },
    "spormidt": {
        "select": jernbane_sql.SPORMIDT_SELECT,
        "create": jernbane_sql.SPORMIDT_CREATE,
        "model": SpormidtProperties,
        "sql_queries": jernbane_sql,
    },
}


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
    model = SQL_MODEL_LOOKUP[collection_id]
    result = await conn.execute(
        " ".join([model["select"], model["sql_queries"].WHERE_ID_EQUALS]),
        params={"lokalid": feature_id},
    )
    row = await result.fetchone()

    if not row:
        raise FeatureNotFoundError(
            f"No element '{feature_id}' in collection {collection_id}."
        )

    return (
        SQL_MODEL_LOOKUP[collection_id]["model"].from_db(row),
        row["main_geometry"],
    )


async def get_feature_collection(
    conn: Connection,
    collection_id: str,
    limit: int,
    after_id: str | None = None,
) -> list:
    """Stream feature collection rows.

    Yields (model, geometry) tuples one at a time, keeping memory
    usage constant regardless of result size. Supports keyset pagination:
    pass after_id to start from the row after the given lokalid, ordered
    by lokalid. limit=None returns all matching rows.
    """
    model = SQL_MODEL_LOOKUP[collection_id]
    result = await conn.execute(
        " ".join([model["select"], model["sql_queries"].AFTER_ID_LIMIT]),
        params={"limit": limit, "after_id": after_id},
    )
    rows = await result.fetchall()
    return [(model["model"].from_db(row), row["main_geometry"]) for row in rows]


async def create_simple_feature(
    conn: Connection, collection_id: str, properties: dict, geometry
):
    model = SQL_MODEL_LOOKUP[collection_id]["model"]
    query = SQL_MODEL_LOOKUP[collection_id]["create"]
    result = await conn.execute(
        query=query,
        params=model.from_post_json(properties).to_create_params(geometry),
    )
    row = await result.fetchone()
    return row["lokalid"]


async def patch_nongeometry_attributes(feature: FeatureGeoJSON, conn: Connection):
    """Patches nongeometry attribute of a feature

    Sketch for arealressursflate. Should be changed later"""
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
            "klassifiseringsmetode": feature.properties["klassifiseringsmetode"].value,
            "oppdateringsdato": feature.properties["oppdateringsdato"],
            "arealtype": feature.properties["arealtype"].value,
            "treslag": feature.properties["treslag"].value,
            "skogbonitet": feature.properties["skogbonitet"].value,
            "grunnforhold": feature.properties["grunnforhold"].value,
            "registreringsversjon": feature.properties["registreringsversjon"],
        },
    )
