import importlib
from pathlib import Path

import psycopg.errors
import pytest
from pygeoapi.process.base import ProcessorExecuteError

from geocomponents.api.db_function_provider import (
    ProviderValidationError,
    _rethrow_pg_raise,
)
from geocomponents.api.pygeoapi_provider import (
    PROVIDER_PATH,
    _field_schema,
    _json_type,
    build_config,
)
from geocomponents.descriptions.loader import load_resolved_datasets
from geocomponents.descriptions.models import ResolvedField
from geocomponents.processes.registry import PROCESS_REGISTRY

DESCRIPTIONS = Path(__file__).resolve().parents[2] / "descriptions"
PUBLIC_URL = "http://example.org/datasets/cadastre/ogc_api"


def _config():
    cad = next(d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "cadastre")
    return build_config(cad, PUBLIC_URL, dsn="postgresql://x")


def test_resources_are_collections_plus_declared_processes():
    cfg = _config()
    # cadastre declares process 'hello' and has a topology collection 'blocks'.
    assert set(cfg["resources"]) == {
        "parcels",
        "buildings",
        "blocks",
        "hello",
        "delete-collection-items",
    }
    assert cfg["resources"]["hello"]["type"] == "process"


def test_delete_collection_process_exposes_only_directly_writable_collections():
    cfg = _config()
    process = cfg["resources"]["delete-collection-items"]

    assert process["type"] == "process"
    assert sorted(process["processor"]["provider_defs"]) == ["buildings", "parcels"]


def test_fkb_bane_config_exposes_batch_upsert_process():
    fkb_bane = next(
        d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "fkb_bane"
    )
    cfg = build_config(
        fkb_bane,
        "http://example.org/datasets/fkb_bane/ogc_api",
        dsn="postgresql://x",
    )
    process = cfg["resources"]["upsert-batch"]
    assert process["type"] == "process"
    assert (
        process["processor"]["provider_defs"]["jernbaneplattformkant"]["collection"]
        == "jernbaneplattformkant"
    )


def test_fkb_bane_config_exposes_import_process_shell():
    fkb_bane = next(
        d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "fkb_bane"
    )
    cfg = build_config(
        fkb_bane,
        "http://example.org/datasets/fkb_bane/ogc_api",
        dsn="postgresql://x",
    )

    process = cfg["resources"]["import"]
    assert process["type"] == "process"
    assert process["processor"]["name"] == PROCESS_REGISTRY["import"]
    assert process["processor"]["dataset"] == "fkb_bane"
    assert process["processor"]["dataset_title"] == "FKB-Bane"


def test_bygning_config_exposes_batch_upsert_process():
    bygning = next(
        d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "bygning"
    )
    cfg = build_config(
        bygning,
        "http://example.org/datasets/bygning/ogc_api",
        dsn="postgresql://x",
    )
    process = cfg["resources"]["upsert-batch"]
    assert process["type"] == "process"
    assert sorted(process["processor"]["provider_defs"]) == [
        "bygning",
        "bygning_omrade",
        "bygning_posisjon",
        "bygning_senterlinje",
    ]


def test_import_processor_matches_gcjobs_shell_metadata_and_is_not_executable():
    module_name, _, class_name = PROCESS_REGISTRY["import"].rpartition(".")
    import_module = importlib.import_module(module_name)
    processor_class = getattr(import_module, class_name)
    processor = processor_class(
        {
            "name": PROCESS_REGISTRY["import"],
            "dataset_title": "FKB-Bane",
        }
    )

    assert processor.metadata["id"] == "import"
    assert processor.metadata["title"] == {"en": "Import FKB-Bane"}
    assert processor.metadata["description"] == {
        "en": "Asynchronously import a multipart upload into the FKB-Bane dataset."
    }
    assert processor.metadata["jobControlOptions"] == ["async-execute"]
    assert processor.metadata["outputs"] == {
        "jobID": {
            "title": "Job ID",
            "description": "Identifier of the accepted import job.",
            "schema": {"type": "string"},
        }
    }
    with pytest.raises(
        ProcessorExecuteError,
        match="gcapi routes import execution to gcjobs",
    ):
        processor.execute({})


def test_processes_are_only_the_declared_ones():
    hydro = next(d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "hydro")
    cfg = build_config(hydro, PUBLIC_URL, dsn="postgresql://x")
    # hydro declares no processes.
    assert all(r["type"] != "process" for r in cfg["resources"].values())


def test_provider_carries_ogc_identifiers_not_physical_names():
    cfg = _config()
    provider = cfg["resources"]["parcels"]["providers"][0]
    assert provider["name"] == PROVIDER_PATH
    assert provider["dataset"] == "cadastre"
    assert provider["collection"] == "parcels"
    assert provider["editable"] is True
    # The provider config never names a table or a per-collection function.
    blob = repr(provider)
    assert "_parcels_items" not in blob
    assert "from cadastre.parcels" not in blob


def test_editable_reflects_feature_model():
    cfg = _config()
    assert cfg["resources"]["parcels"]["providers"][0]["editable"] is True  # simple
    assert cfg["resources"]["blocks"]["providers"][0]["editable"] is False  # topology


def test_server_url_is_the_mount_url_for_correct_links():
    cfg = _config()
    assert cfg["server"]["url"] == PUBLIC_URL


def test_bygning_config_exposes_editable_multilinestring_collection():
    bygning = next(
        d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "bygning"
    )
    cfg = build_config(
        bygning,
        "http://example.org/datasets/bygning/ogc_api",
        dsn="postgresql://x",
    )
    provider = cfg["resources"]["bygning"]["providers"][0]
    assert provider["editable"] is True
    assert provider["geometry_type"] == "MultiLineString"
    assert provider["srid"] == 5972
    assert provider["upsert_field"] == "lokalid"
    assert provider["storage_crs"] == "http://www.opengis.net/def/crs/EPSG/0/5972"
    assert provider["crs"] == [
        "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "http://www.opengis.net/def/crs/EPSG/0/5972",
    ]
    assert provider["always_xy"] is True


def test_bygning_config_exposes_editable_multipolygon_collection():
    bygning = next(
        d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "bygning"
    )
    cfg = build_config(
        bygning,
        "http://example.org/datasets/bygning/ogc_api",
        dsn="postgresql://x",
    )
    provider = cfg["resources"]["bygning_omrade"]["providers"][0]
    assert provider["editable"] is True
    assert provider["geometry_type"] == "MultiPolygon"
    assert provider["srid"] == 5972
    assert provider["upsert_field"] == "lokalid"
    assert provider["storage_crs"] == "http://www.opengis.net/def/crs/EPSG/0/5972"
    assert provider["crs"] == [
        "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "http://www.opengis.net/def/crs/EPSG/0/5972",
    ]
    assert provider["always_xy"] is True


def test_bygning_config_exposes_editable_centerline_collection():
    bygning = next(
        d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "bygning"
    )
    cfg = build_config(
        bygning,
        "http://example.org/datasets/bygning/ogc_api",
        dsn="postgresql://x",
    )
    provider = cfg["resources"]["bygning_senterlinje"]["providers"][0]
    assert provider["editable"] is True
    assert provider["geometry_type"] == "MultiLineString"
    assert provider["srid"] == 5972
    assert provider["upsert_field"] == "lokalid"
    assert provider["storage_crs"] == "http://www.opengis.net/def/crs/EPSG/0/5972"
    assert provider["crs"] == [
        "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "http://www.opengis.net/def/crs/EPSG/0/5972",
    ]
    assert provider["always_xy"] is True


def test_bygning_config_exposes_editable_point_collection():
    bygning = next(
        d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "bygning"
    )
    cfg = build_config(
        bygning,
        "http://example.org/datasets/bygning/ogc_api",
        dsn="postgresql://x",
    )
    provider = cfg["resources"]["bygning_posisjon"]["providers"][0]
    assert provider["editable"] is True
    assert provider["geometry_type"] == "Point"
    assert provider["srid"] == 5972
    assert provider["upsert_field"] == "lokalid"
    assert provider["storage_crs"] == "http://www.opengis.net/def/crs/EPSG/0/5972"
    assert provider["crs"] == [
        "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "http://www.opengis.net/def/crs/EPSG/0/5972",
    ]
    assert provider["always_xy"] is True


def test_fkb_bane_config_exposes_derived_eksternpeker_upsert_field():
    fkb_bane = next(
        d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "fkb_bane"
    )
    cfg = build_config(
        fkb_bane,
        "http://example.org/datasets/fkb_bane/ogc_api",
        dsn="postgresql://x",
    )
    provider = cfg["resources"]["jernbaneplattformkant"]["providers"][0]
    assert provider["editable"] is True
    assert provider["geometry_type"] == "MultiLineString"
    assert provider["srid"] == 5973
    assert provider["upsert_field"] == "identifikasjon.lokalid"
    assert provider["storage_crs"] == "http://www.opengis.net/def/crs/EPSG/0/5973"


def test_wgs84_collections_keep_default_crs_behaviour():
    cfg = _config()
    provider = cfg["resources"]["parcels"]["providers"][0]
    assert "storage_crs" not in provider
    assert "crs" not in provider
    assert "always_xy" not in provider


# --------------------------------------------------------------------------
# _json_type and _field_schema — pre-code suspects (Commit 6)
# --------------------------------------------------------------------------


def test_json_type_jsonb_maps_to_object():
    """Pre-code suspect: jsonb must map to 'object', not the catch-all 'string'."""
    assert _json_type("jsonb") == "object"


def test_field_schema_jsonb_empty_sub_fields_produces_object_with_empty_properties():
    """Pre-code suspect: JSONB with no sub-fields must not raise — emits
    type:object with an empty properties dict."""
    fld = ResolvedField("obj", "jsonb", sub_fields=())
    assert _field_schema(fld) == {"type": "object", "properties": {}}


def test_field_schema_jsonb_depth2_nesting_recurses():
    """Pre-code suspect: JSONB-inside-JSONB must produce nested properties,
    confirming the recursion handles arbitrary depth."""
    inner = ResolvedField("inner", "jsonb", sub_fields=(ResolvedField("x", "text"),))
    outer = ResolvedField("outer", "jsonb", sub_fields=(inner,))
    schema = _field_schema(outer)
    assert schema["properties"]["inner"]["type"] == "object"
    assert schema["properties"]["inner"]["properties"]["x"]["type"] == "string"


def test_field_schema_codelist_values_wins_over_doc_enum():
    """Pre-code suspect: when both codelist_values and enum are set,
    codelist_values (enforced) must appear in the schema enum — not the doc hint."""
    fld = ResolvedField(
        "medium",
        "text",
        codelist_values=("ASFALT", "GRUS"),
        enum=("hint_a", "hint_b"),
    )
    schema = _field_schema(fld)
    assert schema["enum"] == ["ASFALT", "GRUS"]


def test_field_schema_uses_doc_enum_when_no_codelist_values():
    """Pre-code suspect: documented enum hints must appear when there are no
    codelist values, so authors can express constraints without a full CodeList."""
    fld = ResolvedField("medium", "text", enum=("A", "B", "C"))
    schema = _field_schema(fld)
    assert schema["enum"] == ["A", "B", "C"]


# --------------------------------------------------------------------------
# ProviderValidationError + _rethrow_pg_raise (Commit 7)
# --------------------------------------------------------------------------


def test_provider_validation_error_maps_to_422():
    """Pre-code suspect: ProviderValidationError must carry HTTP 422 so pygeoapi
    returns Unprocessable Content, not 500, for DB validation rejections."""
    from http import HTTPStatus

    assert ProviderValidationError().http_status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_rethrow_pg_raise_converts_p0001_to_validation_error():
    """Pre-code suspect: RaiseException (P0001) must be caught and re-raised as
    ProviderValidationError — the gateway contract for validation failures."""
    with pytest.raises(ProviderValidationError), _rethrow_pg_raise():
        raise psycopg.errors.RaiseException()


def test_rethrow_pg_raise_reraises_unknown_sqlstate_unchanged():
    """Pre-code suspect: a RaiseException with a non-P0001 sqlstate must pass
    through — the handler must not swallow unexpected DB errors."""

    class _OtherRaise(psycopg.errors.RaiseException):
        sqlstate = "P9999"

    with pytest.raises(_OtherRaise), _rethrow_pg_raise():
        raise _OtherRaise()
