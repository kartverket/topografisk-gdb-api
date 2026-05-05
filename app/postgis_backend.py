import uuid
from pathlib import Path
from typing import AsyncGenerator, Tuple

from psycopg import Connection, Cursor

from app.models.fkb_bane import (
    JernbaneplattformkantProperties,
    SpormidtProperties,
    json_to_jernbaneplattformkant,
    json_to_spormidt,
)
from app.models.ogc import Geometry

USER_TABLE = "common_users"


class PostGISBackend:
    @staticmethod
    async def initialize_schema(conn: Connection) -> None:
        base_path = Path("app") / "sql"

        # TODO: add nibio db_schema initialisation here.
        # current file (ar5_db_nibio.sql) is a pg_dump and
        # TODO: Decide if files should stay here or somewhere else
        # If here we can loop through and execute using Path().glob()
        # Only thing to be aware is that "fkb_felles" should run first
        # in current setup. glob(".sql") would give wrong order but
        # a rename to "01_fkb_felles.sql", "02_..." would work
        for file in ("fkb_felles", "fkb_bane", "fkb_ar5"):  # fkb_felles first
            await conn.execute(
                (base_path / file).with_suffix(".sql").read_text(encoding="utf-8")
            )

    @staticmethod
    async def create_jernbaneplattformkant(
        properties: dict, geometry: Geometry, conn: Connection
    ) -> JernbaneplattformkantProperties:
        query = """
            INSERT INTO fkb_bane.jernbaneplattformkant (
                lokalid,
                identifikasjon_navnerom,
                identifikasjon_versjonid,
                oppdateringsdato,
                sluttdato,
                datafangstdato,
                verifiseringsdato,
                registreringsversjon,
                informasjon,
                kvalitet_datafangstmetode,
                kvalitet_noyaktighet,
                kvalitet_synbarhet,
                kvalitet_datafangstmetodehoyde,
                kvalitet_noyaktighethoyde,
                grense,
                medium,
                eksternpeker
            )
            VALUES (
                %(lokalid)s,
                %(identifikasjon_navnerom)s,
                %(identifikasjon_versjonid)s,
                %(oppdateringsdato)s,
                %(sluttdato)s,
                %(datafangstdato)s,
                %(verifiseringsdato)s,
                %(registreringsversjon)s,
                %(informasjon)s,
                %(kvalitet_datafangstmetode)s,
                %(kvalitet_noyaktighet)s,
                %(kvalitet_synbarhet)s,
                %(kvalitet_datafangstmetodehoyde)s,
                %(kvalitet_noyaktighethoyde)s,
                ST_Force3D(ST_GeomFromText(%(grense)s)),
                %(medium)s,
                %(eksternpeker)s
            )
            RETURNING lokalid
        """

        jernbaneplattformkant_properties = json_to_jernbaneplattformkant(properties)

        params = {
            "lokalid": uuid.uuid4(),
            "identifikasjon_navnerom": jernbaneplattformkant_properties.identifikasjon.navnerom,
            "identifikasjon_versjonid": jernbaneplattformkant_properties.identifikasjon.versjon_id,
            "oppdateringsdato": jernbaneplattformkant_properties.oppdateringsdato,
            "sluttdato": jernbaneplattformkant_properties.sluttdato,
            "datafangstdato": jernbaneplattformkant_properties.datafangstdato,
            "verifiseringsdato": jernbaneplattformkant_properties.verifiseringsdato,
            "registreringsversjon": jernbaneplattformkant_properties.registreringsversjon,
            "informasjon": jernbaneplattformkant_properties.informasjon,
            "kvalitet_datafangstmetode": jernbaneplattformkant_properties.kvalitet.datafangstmetode,
            "kvalitet_noyaktighet": jernbaneplattformkant_properties.kvalitet.noyaktighet,
            "kvalitet_synbarhet": jernbaneplattformkant_properties.kvalitet.synbarhet,
            "kvalitet_datafangstmetodehoyde": jernbaneplattformkant_properties.kvalitet.datafangstmetode_hoyde,
            "kvalitet_noyaktighethoyde": jernbaneplattformkant_properties.kvalitet.noyaktighet_hoyde,
            "grense": geometry.wkt,
            "medium": jernbaneplattformkant_properties.medium,
            "eksternpeker": jernbaneplattformkant_properties.eksternpeker,
        }

        result = await conn.execute(query=query, params=params)
        row = await result.fetchone()

        if row is None:
            return None

        return row["lokalid"]

    @staticmethod
    async def create_spormidt(properties: dict, geometry: Geometry, conn: Connection):
        query = """
            INSERT INTO fkb_bane.spormidt (
                lokalid,
                identifikasjon_navnerom,
                identifikasjon_versjonid,
                oppdateringsdato,
                sluttdato,
                datafangstdato,
                verifiseringsdato,
                registreringsversjon,
                informasjon,
                kvalitet_datafangstmetode,
                kvalitet_noyaktighet,
                kvalitet_synbarhet,
                kvalitet_datafangstmetodehoyde,
                kvalitet_noyaktighethoyde,
                senterlinje,
                jernbanetype,
                hoydereferanse,
                medium,
                eksternpeker
            )
            VALUES (
                %(lokalid)s,
                %(identifikasjon_navnerom)s,
                %(identifikasjon_versjonid)s,
                %(oppdateringsdato)s,
                %(sluttdato)s,
                %(datafangstdato)s,
                %(verifiseringsdato)s,
                %(registreringsversjon)s,
                %(informasjon)s,
                %(kvalitet_datafangstmetode)s,
                %(kvalitet_noyaktighet)s,
                %(kvalitet_synbarhet)s,
                %(kvalitet_datafangstmetodehoyde)s,
                %(kvalitet_noyaktighethoyde)s,
                ST_Force3D(ST_GeomFromText(%(senterlinje)s)),
                %(jernbanetype)s,
                %(hoydereferanse)s,
                %(medium)s,
                %(eksternpeker)s
            )
            RETURNING lokalid
        """

        spormidt_properties = json_to_spormidt(properties)

        params = {
            "lokalid": uuid.uuid4(),
            "identifikasjon_navnerom": spormidt_properties.identifikasjon.navnerom,
            "identifikasjon_versjonid": spormidt_properties.identifikasjon.versjon_id,
            "oppdateringsdato": spormidt_properties.oppdateringsdato,
            "sluttdato": spormidt_properties.sluttdato,
            "datafangstdato": spormidt_properties.datafangstdato,
            "verifiseringsdato": spormidt_properties.verifiseringsdato,
            "registreringsversjon": spormidt_properties.registreringsversjon,
            "informasjon": spormidt_properties.informasjon,
            "kvalitet_datafangstmetode": spormidt_properties.kvalitet.datafangstmetode,
            "kvalitet_noyaktighet": spormidt_properties.kvalitet.noyaktighet,
            "kvalitet_synbarhet": spormidt_properties.kvalitet.synbarhet,
            "kvalitet_datafangstmetodehoyde": spormidt_properties.kvalitet.datafangstmetode_hoyde,
            "kvalitet_noyaktighethoyde": spormidt_properties.kvalitet.noyaktighet_hoyde,
            "senterlinje": geometry.wkt,
            "jernbanetype": spormidt_properties.jernbanetype,
            "hoydereferanse": spormidt_properties.hoydereferanse,
            "medium": spormidt_properties.medium,
            "eksternpeker": spormidt_properties.eksternpeker,
        }

        result = await conn.execute(query=query, params=params)
        row = await result.fetchone()

        if row is None:
            return None

        return row["lokalid"]
