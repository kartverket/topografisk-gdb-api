from pathlib import Path

from geocomponents.api.pygeoapi_provider import (
    PROVIDER_PATH,
    _field_schema,
    _json_type,
    build_config,
)
from geocomponents.descriptions.loader import load_resolved_datasets
from geocomponents.descriptions.models import ResolvedField

DESCRIPTIONS = Path(__file__).resolve().parents[1] / "descriptions"
PUBLIC_URL = "http://example.org/datasets/cadastre/ogc_api"


def _config():
    cad = next(d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "cadastre")
    return build_config(cad, PUBLIC_URL, dsn="postgresql://x")


def test_resources_are_collections_plus_declared_processes():
    cfg = _config()
    # cadastre declares process 'hello' and has a topology collection 'blocks'.
    assert set(cfg["resources"]) == {"parcels", "buildings", "blocks", "hello"}
    assert cfg["resources"]["hello"]["type"] == "process"


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
