"""
Module storing SQL as queries for use in DAO.
SELECTS should return geometry column as 'main_geometry'
other columns in accordance with pydantic models (later sosi-specs)
"""

# Need to unpack for now because of postgis topology
# TODO: Fix in declarative setup later if possible
COMMON_SELECT = """
SELECT
    -- identity
    identifikasjon_lokal_id::text         AS lokalid,
    identifikasjon_versjon_id::text       AS versjonid,
    identifikasjon_navnerom               AS navnerom,

    -- dates
    datafangstdato,
    verifiseringsdato,
    oppdateringsdato,

    -- text fields
    registreringsversjon,
    opphav,

"""

AREALRESSURSFLATE_SELECT = (
    COMMON_SELECT
    + """
    -- text fields
    klassifiseringsmetode,
    informasjon,
    
    -- enum codes
    arealtype,
    treslag,
    skogbonitet,
    grunnforhold,

    -- geometry
    ST_AsGeoJSON(ST_Transform(omrade::geometry, 4326))::text  AS main_geometry,
    ST_AsGeoJSON(geometry_properties_position)::text          AS posisjon

FROM topo_ar5ngis.face_attributes
"""
)


AREALRESSURSGRENSE_SELECT = (
    COMMON_SELECT
    + """
    -- enum codes
    avgrensing_type,
    
    -- composite
    (topo_ar5ngis.edge_attributes.kvalitet).datafangstmetode      AS datafangstmetode,
    (topo_ar5ngis.edge_attributes.kvalitet).noyaktighet        AS noyaktighet,
    (topo_ar5ngis.edge_attributes.kvalitet).synbarhet          AS synbarhet,

    -- geometry
    ST_AsGeoJSON(ST_Transform(grense::geometry, 4326))::text  AS main_geometry

FROM topo_ar5ngis.edge_attributes
"""
)


WHERE_ID_EQUALS = " WHERE identifikasjon_lokal_id::text = %(lokalid)s"
AFTER_ID_LIMIT = """
    WHERE (%(after_id)s::text IS NULL OR identifikasjon_lokal_id::text > %(after_id)s::text)
    ORDER BY identifikasjon_lokal_id
    LIMIT %(limit)s
"""

AREALRESSURSFLATE_BBOX = """
    WHERE (%(after_id)s::text IS NULL OR identifikasjon_lokal_id::text > %(after_id)s::text)
    AND ST_Intersects(ST_Transform(omrade, 4326), ST_MakeEnvelope(%(lower_left_x)s, %(lower_left_y)s, %(upper_right_x)s, %(upper_right_y)s, 4326))
    ORDER BY identifikasjon_lokal_id
    LIMIT %(limit)s
"""
AREALRESSURSGRENSE_BBOX = """
    WHERE (%(after_id)s::text IS NULL OR identifikasjon_lokal_id::text > %(after_id)s::text)
    AND ST_Intersects(ST_Transform(grense, 4326), ST_MakeEnvelope(%(lower_left_x)s, %(lower_left_y)s, %(upper_right_x)s, %(upper_right_y)s, 4326))
    ORDER BY identifikasjon_lokal_id
    LIMIT %(limit)s
"""
