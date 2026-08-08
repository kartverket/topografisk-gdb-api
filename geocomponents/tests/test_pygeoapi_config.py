from pathlib import Path

from geocomponents.api.pygeoapi_provider import PROVIDER_PATH, build_config
from geocomponents.descriptions.loader import load_resolved_datasets

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
    assert provider["upsert_key"] == ["lokalid", "identifikasjon_navnerom"]
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
    assert provider["upsert_key"] == ["lokalid", "identifikasjon_navnerom"]
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
    assert provider["upsert_key"] == ["lokalid", "identifikasjon_navnerom"]
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
    assert provider["upsert_key"] == ["lokalid", "identifikasjon_navnerom"]
    assert provider["storage_crs"] == "http://www.opengis.net/def/crs/EPSG/0/5972"
    assert provider["crs"] == [
        "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
        "http://www.opengis.net/def/crs/EPSG/0/5972",
    ]
    assert provider["always_xy"] is True


def test_wgs84_collections_keep_default_crs_behaviour():
    cfg = _config()
    provider = cfg["resources"]["parcels"]["providers"][0]
    assert "storage_crs" not in provider
    assert "crs" not in provider
    assert "always_xy" not in provider
