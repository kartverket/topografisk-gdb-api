from enum import Enum
from typing import Optional

import orjson
from pydantic import Field

from app.models.fkb_felles import (
    CaseInsensitiveStrEnum,
    FKBFelles,
    Identifikasjon,
    Posisjonskvalitet,
)


class ArealressursArealtype(Enum):
    bebygd = "11"
    samferdsel = "12"
    fulldyrka_jord = "21"
    overflatedyrka_jord = "22"
    innmarksbeite = "23"
    skog = "30"
    apen_fastmark = "50"
    myr = "60"
    snoisbre = "70"
    ferskvann = "81"
    hav = "82"
    ikke_kartlagt = "99"


class ArealressursTreslag(Enum):
    barskog = "31"
    lauvskog = "32"
    blandingsskog = "33"
    ikke_tresatt = "39"
    ikke_relevant = "98"
    ikke_registrert = "99"


class ArealressursSkogbonitet(Enum):
    impediment = "11"
    lav = "12"
    middels = "13"
    hoy = "14"
    sars_hoy = "15"
    ikke_relevant = "98"
    ikke_registrert = "99"


class ArealressursGrunnforhold(Enum):
    blokkmark = "41"
    fjell_i_dagen = "42"
    grunnlendt = "43"
    jorddekt = "44"
    organisk_jordlag = "45"
    konstruert = "46"
    ikke_relevant = "98"
    ikke_registrert = "99"


class Klassifiseringsmetode(CaseInsensitiveStrEnum):
    sOrto = "sOrto"
    uOrto = "uOrto"
    sFelt = "sFelt"
    uFjern = "uFjern"
    uMeld = "uMeld"
    uAnnen = "uAnnen"


class ArealressursGrense(FKBFelles):
    avgrensing_type: str
    kvalitet: Posisjonskvalitet


class ArealressursFiktiv(FKBFelles):
    pass


class ArealressursFlate(FKBFelles):
    arealtype: ArealressursArealtype
    treslag: ArealressursTreslag
    skogbonitet: ArealressursSkogbonitet
    grunnforhold: ArealressursGrunnforhold
    klassifiseringsmetode: Klassifiseringsmetode
    posisjon: Optional[dict] = (
        Field(
            None, json_schema_extra={"type": "object", "description": "GeoJSON Point"}
        ),
    )


def db_to_arealressurs_flate(row: dict, posisjon: str) -> ArealressursFlate:
    return ArealressursFlate(
        identifikasjon=Identifikasjon(
            lokal_id=row["lokalid"],
            navnerom=row["identifikasjon_navnerom"],
            versjon_id=row["identifikasjon_versjonid"],
        ),
        oppdateringsdato=row["oppdateringsdato"],
        datafangstdato=row["datafangstdato"],
        arealtype=row["arealtype"],
        treslag=row["treslag"],
        skogbonitet=row["skogbonitet"],
        grunnforhold=row["grunnforhold"],
        klassifiseringsmetode=row["klassifiseringsmetode"],
        posisjon=orjson.loads(posisjon) if posisjon else None,
    )
