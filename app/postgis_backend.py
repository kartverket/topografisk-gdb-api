from typing import Tuple, List
from pathlib import Path
import uuid

from psycopg import Connection

from app.models.ogc import Geometry
from app.models.fkb_bane import (
    JernbaneplattformkantProperties,
    SpormidtProperties,
    db_to_jernbaneplattformkant,
    db_to_spormidt,
    json_to_jernbaneplattformkant,
    json_to_spormidt
)
from app.models.exceptions import FeatureNotFoundError

USER_TABLE = "common_users"

class PostGISBackend:
    @staticmethod
    async def initialize_schema(conn: Connection) -> None:
        fkb_felles_path = Path("app") / "sql/fkb_felles.sql"
        fkb_felles = fkb_felles_path.read_text(encoding="utf-8")
        await conn.execute(fkb_felles)

        fkb_bane_path = Path("app") / "sql/fkb_bane.sql"
        fkb_bane = fkb_bane_path.read_text(encoding="utf-8")
        await conn.execute(fkb_bane)

        fkb_ar5_path = Path("app") / "sql/fkb_ar5.sql"
        fkb_ar5 = fkb_ar5_path.read_text(encoding="utf-8")
        await conn.execute(fkb_ar5)

    @staticmethod
    async def get_jernbaneplattformkant(id: str, conn: Connection) -> Tuple[JernbaneplattformkantProperties, dict]:
        result = await conn.execute(
            query=f"""
                SELECT *, ST_AsGeoJSON(grense)::json AS grense_geojson FROM fkb_bane.jernbaneplattformkant 
                WHERE lokalid = %(id)s
            """,
            params={"id": id}
        )
        jernbaneplattformkant_row = await result.fetchone()

        if not jernbaneplattformkant_row:
            raise FeatureNotFoundError()

        return db_to_jernbaneplattformkant(jernbaneplattformkant_row), jernbaneplattformkant_row["grense_geojson"]
    
    @staticmethod
    async def get_all_jernbaneplattformkant(conn: Connection) -> List[Tuple[JernbaneplattformkantProperties, dict]]:
        result = await conn.execute(
            query=f"""
                SELECT *, ST_AsGeoJSON(grense)::json AS grense_geojson FROM fkb_bane.jernbaneplattformkant
            """
        )
        jernbaneplattformkant_rows = await result.fetchall()

        return list(map(
            lambda row: (db_to_jernbaneplattformkant(row), row["grense_geojson"]),
            jernbaneplattformkant_rows
        ))
    
    @staticmethod
    async def create_jernbaneplattformkant(properties: dict, geometry: Geometry, conn: Connection) -> JernbaneplattformkantProperties:
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
    async def get_spormidt(id: str, conn: Connection) -> Tuple[SpormidtProperties, dict]:
        result = await conn.execute(
            query=f"""
                SELECT *, ST_AsGeoJSON(senterlinje)::json AS senterlinje_geojson FROM fkb_bane.spormidt
                WHERE lokalid = %(id)s
            """,
            params={"id": id}
        )
        spormidt_row = await result.fetchone()

        if not spormidt_row:
            raise FeatureNotFoundError()
            
        return db_to_spormidt(spormidt_row), spormidt_row["senterlinje_geojson"]
    
    @staticmethod
    async def get_all_spormidt(conn: Connection) -> List[Tuple[SpormidtProperties, dict]]:
        result = await conn.execute(
            query=f"""
                SELECT *, ST_AsGeoJSON(senterlinje)::json AS senterlinje_geojson FROM fkb_bane.spormidt
            """
        )
        spormidt_rows = await result.fetchall()

        return list(map(
            lambda row: (db_to_spormidt(row), row["senterlinje_geojson"]),
            spormidt_rows
        ))
    
    @staticmethod
    async def create_sportmidt(properties: dict, geometry: Geometry, conn: Connection):
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
