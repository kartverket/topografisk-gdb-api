"""
FKB-Bane 5.0.1 — hand-written Pydantic models.
Source: https://sosi.geonorge.no/Produktspesifikasjoner/FKB-Bane/5.0.1/
"""

from typing import Optional

from pydantic import Field

from app.models.fkb_felles import (
    FKBFelles,
    Posisjonskvalitet,
    Identifikasjon,
    CaseInsensitiveStrEnum,
    Datafangstmetode
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


# https://sosi.geonorge.no/Produktspesifikasjoner/FKB-Bane/5.0.1/#spormidt
class SpormidtProperties(FKBFelles):
    # senterlinje: GM_Curve — in GeoJSON geometry, not properties
    kvalitet: Posisjonskvalitet
    medium: Medium
    eksternpeker: Optional[str] = None
    jernbanetype: Jernbanetype
    hoydereferanse: Hoydereferanse = Field(alias="høydereferanse")

def db_to_jernbaneplattformkant(dict: dict) -> JernbaneplattformkantProperties:
        return JernbaneplattformkantProperties(
            identifikasjon=Identifikasjon(
                lokal_id=dict["lokalid"],
                navnerom=dict["identifikasjon_navnerom"],
                versjon_id=dict["identifikasjon_versjonid"]
            ),
            oppdateringsdato=dict["oppdateringsdato"],
            datafangstdato=dict["datafangstdato"],
            kvalitet=Posisjonskvalitet(
                datafangstmetode=Datafangstmetode(dict["kvalitet_datafangstmetode"])
            ),
            medium=Medium(dict["medium"])
        )

def json_to_jernbaneplattformkant(dict: dict) -> JernbaneplattformkantProperties:
        return JernbaneplattformkantProperties(
            identifikasjon=Identifikasjon(
                lokal_id=dict["identifikasjon"]["lokalId"],
                navnerom=dict["identifikasjon"]["navnerom"],
                versjon_id=dict["identifikasjon"]["versjonId"]
            ),
            oppdateringsdato=dict["oppdateringsdato"],
            datafangstdato=dict["datafangstdato"],
            kvalitet=Posisjonskvalitet(
                datafangstmetode=Datafangstmetode(dict["kvalitet"]["datafangstmetode"])
            ),
            medium=Medium(dict["medium"])
        )

def db_to_spormidt(dict: dict) -> SpormidtProperties:
        return SpormidtProperties(
            identifikasjon=Identifikasjon(
                lokal_id=dict["lokalid"],
                navnerom=dict["identifikasjon_navnerom"],
                versjon_id=dict["identifikasjon_versjonid"]
            ),
            oppdateringsdato=dict["oppdateringsdato"],
            datafangstdato=dict["datafangstdato"],
            kvalitet=Posisjonskvalitet(
                datafangstmetode=Datafangstmetode(dict["kvalitet_datafangstmetode"])
            ),
            medium=Medium(dict["medium"]),
            jernbanetype=Jernbanetype(dict["jernbanetype"]),
            hoydereferanse=Hoydereferanse(dict["hoydereferanse"])
        )

def json_to_spormidt(dict: dict) -> SpormidtProperties:
        return SpormidtProperties(
            identifikasjon=Identifikasjon(
                lokal_id=dict["identifikasjon"]["lokalId"],
                navnerom=dict["identifikasjon"]["navnerom"],
                versjon_id=dict["identifikasjon"]["versjonId"]
            ),
            oppdateringsdato=dict["oppdateringsdato"],
            datafangstdato=dict["datafangstdato"],
            kvalitet=Posisjonskvalitet(
                datafangstmetode=Datafangstmetode(dict["kvalitet"]["datafangstmetode"])
            ),
            medium=Medium(dict["medium"]),
            jernbanetype=Jernbanetype(dict["jernbanetype"]),
            hoydereferanse=Hoydereferanse(dict["høydereferanse"])
        )
