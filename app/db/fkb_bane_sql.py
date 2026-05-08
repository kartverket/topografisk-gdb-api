JERNBANEPLATTFORM_SELECT = "SELECT *, ST_AsGeoJSON(grense)::text AS main_geometry FROM fkb_bane.jernbaneplattformkant"
SPORMIDT_SELECT = (
    "SELECT *, ST_AsGeoJSON(senterlinje)::text AS main_geometry FROM fkb_bane.spormidt"
)
WHERE_ID_EQUALS = " WHERE lokalid = %(lokalid)s"
AFTER_ID_LIMIT = """
    WHERE (%(after_id)s::text IS NULL OR lokalid::text > %(after_id)s::text)
    ORDER BY lokalid
    LIMIT %(limit)s
"""
JERNBANEPLATTFORM_BBOX = """
    WHERE (%(after_id)s::text IS NULL OR lokalid::text > %(after_id)s::text)
    AND ST_Intersects(ST_Transform(grense, 4326), ST_MakeEnvelope(%(lower_left_x)s, %(lower_left_y)s, %(upper_right_x)s, %(upper_right_y)s, 4326))
    ORDER BY lokalid
    LIMIT %(limit)s
"""
SPORMIDT_BBOX = """
    WHERE (%(after_id)s::text IS NULL OR lokalid::text > %(after_id)s::text)
    AND ST_Intersects(ST_Transform(senterlinje, 4326), ST_MakeEnvelope(%(lower_left_x)s, %(lower_left_y)s, %(upper_right_x)s, %(upper_right_y)s, 4326))
    ORDER BY lokalid
    LIMIT %(limit)s
"""

CREATE_COMMON_NAMES = """
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
"""
CREATE_COMMON_VALUES = """
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
"""
SPORMIDT_CREATE = " ".join(
    [
        "INSERT INTO fkb_bane.spormidt (",
        CREATE_COMMON_NAMES,
        "senterlinje, jernbanetype, hoydereferanse, medium, eksternpeker)",
        "VALUES (",
        CREATE_COMMON_VALUES,
        """ 
        ST_Force3D(ST_GeomFromText(%(senterlinje)s)),
        %(jernbanetype)s,
        %(hoydereferanse)s,
        %(medium)s,
        %(eksternpeker)s
        )
        RETURNING lokalid""",
    ]
)

JERNBANEPLATTFORM_CREATE = " ".join(
    [
        "INSERT INTO fkb_bane.jernbaneplattformkant (",
        CREATE_COMMON_NAMES,
        "grense, medium, eksternpeker)",
        "VALUES (",
        CREATE_COMMON_VALUES,
        """
        ST_Force3D(ST_GeomFromText(%(grense)s)),
        %(medium)s,
        %(eksternpeker)s
        )
        RETURNING lokalid
    """,
    ]
)
