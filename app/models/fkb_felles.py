import datetime
from enum import Enum, StrEnum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CaseInsensitiveStrEnum(StrEnum):
    """Enums inheriting from this class becomes case insensitive for input
    but return their given value


    >>> class MyEnum(FKBEnum):
    ...    value = 'value'
    ...
    >>> my_enum = MyEnum("vaLUe")
    >>> my_enum.value
    'value'
    """

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            for member in cls:
                if member.value.casefold() == value.casefold():
                    return member
        return None

    # https://register.geonorge.no/sosi-kodelister/fkb/generell/5.0/datafangstmetode


class Datafangstmetode(CaseInsensitiveStrEnum):
    dig = "dig"  # Digitalisert fra ortofoto / plane kartdata
    fot = "fot"  # Fotogrammetri
    gen = "gen"  # Generert (ML, punktsky, bildematching m.m.)
    lan = "lan"  # Landmålt (nivellering, vinkelmåling, GNSS)
    pla = "pla"  # Plandata uten feltkontroll
    sat = "sat"  # Satellittmålt — direkte GNSS
    byg = "byg"  # Som bygget — BIM/prosjektert, kontrollert i felt
    ukj = "ukj"  # Ukjent


# https://register.geonorge.no/sosi-kodelister/fkb/generell/5.0/synbarhet
class Synbarhet(Enum):
    fullt_synlig = 0  # Fullt synlig / gjenfinnbart
    vanskelig = 1  # Vanskelig å definere presist
    middels = 2  # Middels synlig / gjenkjennbart
    ikke_synlig = 3  # Ikke synlig / gjenkjennbart


class FKBBase(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,  # accept both Python name and alias
        alias_generator=None,  # explicit aliases only — no auto-camel-case
    )


# https://sosi.geonorge.no/Produktspesifikasjoner/FKB-Bane/5.0.1/#identifikasjon
class Identifikasjon(FKBBase):
    lokal_id: str = Field(alias="lokalId")
    navnerom: str
    versjon_id: Optional[str] = Field(None, alias="versjonId")


# https://sosi.geonorge.no/Produktspesifikasjoner/FKB-Bane/5.0.1/#posisjonskvalitet
class Posisjonskvalitet(FKBBase):
    datafangstmetode: Datafangstmetode
    noyaktighet: Optional[int] = Field(None, alias="nøyaktighet")
    synbarhet: Optional[Synbarhet] = None
    datafangstmetode_hoyde: Optional[Datafangstmetode] = Field(
        None, alias="datafangstmetodeHøyde"
    )
    noyaktighet_hoyde: Optional[int] = Field(None, alias="nøyaktighetHøyde")


class FKBFelles(FKBBase):
    identifikasjon: Identifikasjon
    oppdateringsdato: datetime.datetime
    sluttdato: Optional[datetime.datetime] = None
    datafangstdato: datetime.date
    verifiseringsdato: Optional[datetime.date] = None
    registreringsversjon: Optional[str] = None
    informasjon: Optional[str] = None

    @field_validator("datafangstdato", "verifiseringsdato", mode="before")
    @classmethod
    def coerce_to_date(cls, v):
        if isinstance(v, datetime.datetime):
            return v.date()
        return v
