"""
FKB-Bane 5.0.1 — hand-written Pydantic models.
Source: https://sosi.geonorge.no/Produktspesifikasjoner/FKB-Bane/5.0.1/
"""

import uuid
from typing import Optional

from pydantic import Field

from app.models.fkb_felles import (
    CaseInsensitiveStrEnum,
    Datafangstmetode,
    FKBFelles,
    Identifikasjon,
    Posisjonskvalitet,
)


# https://register.geonorge.no/sosi-kodelister/fkb/generell/5.0/medium
class Medium(CaseInsensitiveStrEnum):
    D = "D"  # Delvis i eller under vann
    B = "B"  # I eller på bygning / bygningsmessig anlegg
    L = "L"  # I lufta
    V = "V"  # Alltid i vann
    I = "I"  # På isbre  # noqa
    T = "T"  # På terrenget / bakkenivå
    X = "X"  # Ukjent plassering
    U = "U"  # Under terrenget


# https://register.geonorge.no/sosi-kodelister/fkb/bane/5.0/jernbanetype
class Jernbanetype(CaseInsensitiveStrEnum):
    F = "F"  # Forstadsbane — mellomting bane/metro/trikk (f.eks. Bybanen)
    J = "J"  # Jernbane — konvensjonell tog
    K = "K"  # Kabelbane (f.eks. Fløibanen)
    S = "S"  # Sporveg — trikk
    T = "T"  # Tunnelbane — metro / T-bane


# https://register.geonorge.no/sosi-kodelister/fkb/generell/5.0/hoydereferanse
class Hoydereferanse(CaseInsensitiveStrEnum):
    fot = "fot"  # Høyden målt til foten/bunnen av objektet
    topp = "topp"  # Høyden målt til toppen av objektet
    ukjent = "ukjent"


# ---------------------------------------------------------------------------
# Feature types
# ---------------------------------------------------------------------------


# https://sosi.geonorge.no/Produktspesifikasjoner/FKB-Bane/5.0.1/#jernbaneplattformkant
class JernbaneplattformkantProperties(FKBFelles):
    # grense: GM_Curve — in GeoJSON geometry, not properties
    kvalitet: Posisjonskvalitet
    medium: Medium
    eksternpeker: Optional[str] = None

    @staticmethod
    def from_db(row: dict) -> "JernbaneplattformkantProperties":
        return JernbaneplattformkantProperties(
            identifikasjon=Identifikasjon(
                lokal_id=row["lokalid"],
                navnerom=row["identifikasjon_navnerom"],
                versjon_id=row["identifikasjon_versjonid"],
            ),
            oppdateringsdato=row["oppdateringsdato"],
            datafangstdato=row["datafangstdato"],
            kvalitet=Posisjonskvalitet(
                datafangstmetode=Datafangstmetode(row["kvalitet_datafangstmetode"])
            ),
            medium=Medium(row["medium"]),
        )

    @staticmethod
    def from_post_json(post_json: dict) -> "JernbaneplattformkantProperties":
        return JernbaneplattformkantProperties(
            identifikasjon=Identifikasjon(
                lokal_id=post_json["identifikasjon"]["lokalId"],
                navnerom=post_json["identifikasjon"]["navnerom"],
                versjon_id=post_json["identifikasjon"]["versjonId"],
            ),
            oppdateringsdato=post_json["oppdateringsdato"],
            datafangstdato=post_json["datafangstdato"],
            kvalitet=Posisjonskvalitet(
                datafangstmetode=Datafangstmetode(
                    post_json["kvalitet"]["datafangstmetode"]
                )
            ),
            medium=Medium(post_json["medium"]),
        )

    def to_create_params(self, geometry) -> dict:
        """Create params for sql-create query

        Temporary solution. Do not be afraid to change
        SHould mostly disappear long term.
        """
        return {
            "lokalid": uuid.uuid4(),
            "identifikasjon_navnerom": self.identifikasjon.navnerom,
            "identifikasjon_versjonid": self.identifikasjon.versjon_id,
            "oppdateringsdato": self.oppdateringsdato,
            "sluttdato": self.sluttdato,
            "datafangstdato": self.datafangstdato,
            "verifiseringsdato": self.verifiseringsdato,
            "registreringsversjon": self.registreringsversjon,
            "informasjon": self.informasjon,
            "kvalitet_datafangstmetode": self.kvalitet.datafangstmetode,
            "kvalitet_noyaktighet": self.kvalitet.noyaktighet,
            "kvalitet_synbarhet": self.kvalitet.synbarhet,
            "kvalitet_datafangstmetodehoyde": self.kvalitet.datafangstmetode_hoyde,
            "kvalitet_noyaktighethoyde": self.kvalitet.noyaktighet_hoyde,
            "grense": geometry.wkt,
            "medium": self.medium,
            "eksternpeker": self.eksternpeker,
        }


# https://sosi.geonorge.no/Produktspesifikasjoner/FKB-Bane/5.0.1/#spormidt
class SpormidtProperties(FKBFelles):
    # senterlinje: GM_Curve — in GeoJSON geometry, not properties
    kvalitet: Posisjonskvalitet
    medium: Medium
    eksternpeker: Optional[str] = None
    jernbanetype: Jernbanetype
    hoydereferanse: Hoydereferanse = Field(alias="høydereferanse")

    @staticmethod
    def from_db(row: dict) -> "SpormidtProperties":
        return SpormidtProperties(
            identifikasjon=Identifikasjon(
                lokal_id=row["lokalid"],
                navnerom=row["identifikasjon_navnerom"],
                versjon_id=row["identifikasjon_versjonid"],
            ),
            oppdateringsdato=row["oppdateringsdato"],
            datafangstdato=row["datafangstdato"],
            kvalitet=Posisjonskvalitet(
                datafangstmetode=Datafangstmetode(row["kvalitet_datafangstmetode"])
            ),
            medium=Medium(row["medium"]),
            jernbanetype=Jernbanetype(row["jernbanetype"]),
            hoydereferanse=Hoydereferanse(row["hoydereferanse"]),
        )

    @staticmethod
    def from_post_json(post_json: dict) -> "SpormidtProperties":
        return SpormidtProperties(
            identifikasjon=Identifikasjon(
                lokal_id=post_json["identifikasjon"]["lokalId"],
                navnerom=post_json["identifikasjon"]["navnerom"],
                versjon_id=post_json["identifikasjon"]["versjonId"],
            ),
            oppdateringsdato=post_json["oppdateringsdato"],
            datafangstdato=post_json["datafangstdato"],
            kvalitet=Posisjonskvalitet(
                datafangstmetode=Datafangstmetode(
                    post_json["kvalitet"]["datafangstmetode"]
                )
            ),
            medium=Medium(post_json["medium"]),
            jernbanetype=Jernbanetype(post_json["jernbanetype"]),
            hoydereferanse=Hoydereferanse(post_json["høydereferanse"]),
        )

    def to_create_params(self, geometry) -> dict:
        """Create params for sql-create query

        Temporary solution. Do not be afraid to change
        SHould mostly disappear long term.
        """
        return {
            "lokalid": uuid.uuid4(),  # This should not happen at db-level
            "identifikasjon_navnerom": self.identifikasjon.navnerom,
            "identifikasjon_versjonid": self.identifikasjon.versjon_id,
            "oppdateringsdato": self.oppdateringsdato,
            "sluttdato": self.sluttdato,
            "datafangstdato": self.datafangstdato,
            "verifiseringsdato": self.verifiseringsdato,
            "registreringsversjon": self.registreringsversjon,
            "informasjon": self.informasjon,
            "kvalitet_datafangstmetode": self.kvalitet.datafangstmetode,
            "kvalitet_noyaktighet": self.kvalitet.noyaktighet,
            "kvalitet_synbarhet": self.kvalitet.synbarhet,
            "kvalitet_datafangstmetodehoyde": self.kvalitet.datafangstmetode_hoyde,
            "kvalitet_noyaktighethoyde": self.kvalitet.noyaktighet_hoyde,
            "senterlinje": geometry.wkt,
            "jernbanetype": self.jernbanetype,
            "hoydereferanse": self.hoydereferanse,
            "medium": self.medium,
            "eksternpeker": self.eksternpeker,
        }
