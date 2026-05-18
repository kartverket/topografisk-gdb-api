-- Featurizer functions for AR5 collections.
-- These live in ar5_api schema, separate from the NIBIO topology schema (topo_ar5ngis).
-- Each function takes a full table row and a target SRID, and returns a GeoJSON Feature as jsonb.
-- Usage: SELECT ar5_api.arealressursflate_feature(t.*, 4326)::text FROM topo_ar5ngis.face_attributes t WHERE ...
-- Default target_srid is 4326 (WGS84). Pass a different SRID to support CRS negotiation.

CREATE SCHEMA IF NOT EXISTS ar5_api;


-- ArealressursFlate (land-use polygons)
-- Source table: topo_ar5ngis.face_attributes
-- Geometry: omrade (topogeometry, areal) — cast to geometry before transform
-- No kvalitet — SOSI spec does not include it on surfaces (surfaces derive quality from their bounding edges)
CREATE OR REPLACE FUNCTION ar5_api.arealressursflate_feature(
    r topo_ar5ngis.face_attributes,
    target_srid integer DEFAULT 4326
)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
SELECT jsonb_build_object(
    'type',       'Feature',
    'id',         r.identifikasjon_lokal_id,
    'geometry',   ST_AsGeoJSON(ST_Transform(r.omrade::geometry, target_srid))::jsonb,
    'properties', jsonb_build_object(
        'identifikasjon', jsonb_build_object(
            'lokalId',   r.identifikasjon_lokal_id,
            'navnerom',  r.identifikasjon_navnerom,
            'versjonId', r.identifikasjon_versjon_id
        ),
        'featuretype',           r.featuretype,
        'kartstandard',          r.kartstandard,
        'datafangstdato',        r.datafangstdato,
        'verifiseringsdato',     r.verifiseringsdato,
        'oppdateringsdato',      r.oppdateringsdato,
        'opphav',                r.opphav,
        'informasjon',           r.informasjon,
        'klassifiseringsmetode', r.klassifiseringsmetode,
        'registreringsversjon',  r.registreringsversjon,
        'arealtype',             r.arealtype,
        'treslag',               r.treslag,
        'skogbonitet',           r.skogbonitet,
        'grunnforhold',          r.grunnforhold,
        'posisjon',              ST_AsGeoJSON(ST_Transform(r.geometry_properties_position, target_srid))::jsonb
    )
)
$$;


-- ArealressursGrense (land-use boundary lines)
-- Source table: topo_ar5ngis.edge_attributes
-- Geometry: grense (topogeometry, lineal) — cast to geometry before transform
-- Includes kvalitet composite — SOSI spec places quality on the bounding edges, not the surfaces
-- No: kartstandard, informasjon, klassifiseringsmetode, posisjon, or AR5 enum columns (arealtype etc.)
CREATE OR REPLACE FUNCTION ar5_api.arealressursgrense_feature(
    r topo_ar5ngis.edge_attributes,
    target_srid integer DEFAULT 4326
)
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
SELECT jsonb_build_object(
    'type',       'Feature',
    'id',         r.identifikasjon_lokal_id,
    'geometry',   ST_AsGeoJSON(ST_Transform(r.grense::geometry, target_srid))::jsonb,
    'properties', jsonb_build_object(
        'identifikasjon', jsonb_build_object(
            'lokalId',   r.identifikasjon_lokal_id,
            'navnerom',  r.identifikasjon_navnerom,
            'versjonId', r.identifikasjon_versjon_id
        ),
        'featuretype',        r.featuretype,
        'datafangstdato',     r.datafangstdato,
        'verifiseringsdato',  r.verifiseringsdato,
        'oppdateringsdato',   r.oppdateringsdato,
        'opphav',             r.opphav,
        'registreringsversjon', r.registreringsversjon,
        'avgrensing_type',    r.avgrensing_type,
        'kvalitet', jsonb_build_object(
            'datafangstmetode', (r.kvalitet).datafangstmetode,
            'noyaktighet',      (r.kvalitet).noyaktighet,
            'synbarhet',        (r.kvalitet).synbarhet
        )
    )
)
$$;
