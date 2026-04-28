-- Alter enum code columns from smallint to text.
--
-- NIBIO stores arealtype/treslag/skogbonitet/grunnforhold/avgrensing_type as
-- smallint but treats them as string codes in every view (::VARCHAR casts
-- throughout) and in the topology engine (format('%L', ...) produces quoted
-- string literals). Storing as text aligns schema with actual use.
--
-- Views that depend on these columns must be dropped and recreated.
-- The ::VARCHAR casts in the original view bodies are removed — text::varchar
-- is a no-op and would just be noise.

DROP VIEW IF EXISTS topo_ar5ngis.face_attributes_export_fkb50;
DROP VIEW IF EXISTS topo_ar5ngis.edge_attributes_export_fkb50;
DROP VIEW IF EXISTS topo_ar5ngis.ngis_export_data_flate_v;
DROP VIEW IF EXISTS topo_ar5ngis.ngis_export_data_grense_v;
-- Table below is used in nibio integration tests but not necessary
DROP VIEW IF EXISTS topo_ar5ngis.webclient_flate_topojson_flate_v;

ALTER TABLE topo_ar5ngis.face_attributes
ALTER COLUMN arealtype TYPE text USING arealtype::text,
ALTER COLUMN treslag TYPE text USING treslag::text,
ALTER COLUMN skogbonitet TYPE text USING skogbonitet::text,
ALTER COLUMN grunnforhold TYPE text USING grunnforhold::text,
ALTER COLUMN registreringsversjon TYPE text USING registreringsversjon::text;

ALTER TABLE topo_ar5ngis.edge_attributes
ALTER COLUMN avgrensing_type TYPE text USING avgrensing_type::text;

-- Recreate views with ::VARCHAR casts removed (columns are now text).

CREATE OR REPLACE VIEW topo_ar5ngis.ngis_export_data_flate_v AS
SELECT
    featuretype,
    identifikasjon_lokal_id::uuid,
    identifikasjon_navnerom,
    identifikasjon_versjon_id::timestamp,
    kartstandard,
    datafangstdato,
    verifiseringsdato,
    oppdateringsdato::timestamp,
    opphav,
    kvalitet,
    arealtype,
    treslag,
    skogbonitet,
    grunnforhold,
    registreringsversjon,
    omrade,
    COALESCE(informasjon, '') AS informasjon
FROM topo_ar5ngis.face_attributes;

CREATE OR REPLACE VIEW topo_ar5ngis.ngis_export_data_grense_v AS
SELECT
    featuretype,
    identifikasjon_lokal_id,
    identifikasjon_navnerom,
    identifikasjon_versjon_id::timestamp,
    datafangstdato,
    verifiseringsdato,
    oppdateringsdato::timestamp,
    opphav,
    kvalitet,
    avgrensing_type,
    registreringsversjon,
    grense
FROM topo_ar5ngis.edge_attributes;

CREATE OR REPLACE VIEW topo_ar5ngis.face_attributes_export_fkb50 AS
SELECT
    identifikasjon_lokal_id AS id,
    identifikasjon_navnerom,
    arealtype,
    treslag,
    skogbonitet,
    grunnforhold,
    datafangstdato,
    oppdateringsdato::timestamp,
    verifiseringsdato,
    opphav,
    klassifiseringsmetode,
    informasjon,
    1 AS editable,
    featuretype,
    registreringsversjon,
    identifikasjon_lokal_id,
    omrade,
    FORMAT('%s000', identifikasjon_versjon_id::timestamp) AS identifikasjon_versjon_id
FROM topo_ar5ngis.face_attributes;

CREATE OR REPLACE VIEW topo_ar5ngis.edge_attributes_export_fkb50 AS
SELECT
    featuretype,
    identifikasjon_lokal_id,
    identifikasjon_navnerom,
    datafangstdato,
    verifiseringsdato,
    oppdateringsdato::timestamp,
    opphav,
    kvalitet,
    avgrensing_type,
    registreringsversjon,
    grense,
    FORMAT('%s000', identifikasjon_versjon_id::timestamp) AS identifikasjon_versjon_id
FROM topo_ar5ngis.edge_attributes;
