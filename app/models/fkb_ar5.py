from enum import Enum

from app.models.fkb_felles import (
    FKBFelles,
    Posisjonskvalitet,
    CaseInsensitiveStrEnum,
    Identifikasjon
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

def db_to_arealressurs_flate(dict: dict) -> ArealressursFlate:
        return ArealressursFlate(
            identifikasjon=Identifikasjon(
                lokal_id=dict["lokalid"],
                navnerom=dict["identifikasjon_navnerom"],
                versjon_id=dict["identifikasjon_versjonid"]
            ),
            oppdateringsdato=dict["oppdateringsdato"],
            datafangstdato=dict["datafangstdato"],
            arealtype=dict["arealtype"],
            treslag=dict["treslag"],
            skogbonitet=dict["skogbonitet"],
            grunnforhold=dict["grunnforhold"],
            klassifiseringsmetode=dict["klassifiseringsmetode"]
        )
