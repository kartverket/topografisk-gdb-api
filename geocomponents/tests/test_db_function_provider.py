from math import isclose

import pyproj
from pygeoapi.crs import create_crs_transform_spec

from geocomponents.api.db_function_provider import DbFunctionProvider


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        return None

    def fetchone(self):
        return [self._row]


class _FakeConnection:
    def __init__(self, row):
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self._row)


def test_query_transforms_projected_storage_crs_to_default_crs84(monkeypatch):
    provider_def = {
        "type": "feature",
        "name": "geocomponents.api.db_function_provider.DbFunctionProvider",
        "data": "postgresql://ignored",
        "dataset": "bygning",
        "collection": "bygning",
        "id_field": "id",
        "geom_field": "geometry",
        "geometry_type": "MultiLineString",
        "srid": 5972,
        "storage_crs": "http://www.opengis.net/def/crs/EPSG/0/5972",
        "crs": [
            "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
            "http://www.opengis.net/def/crs/EPSG/0/5972",
        ],
        "always_xy": True,
        "fields": {},
    }
    provider = DbFunctionProvider(provider_def)
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "f1",
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": [
                        [
                            [526131.4498, 6849490.719999999, 402.2],
                            [526131.1098, 6849497.649999998, 402.2],
                        ]
                    ],
                },
                "properties": {"objtype": "Mønelinje"},
            }
        ],
        "numberReturned": 1,
        "numberMatched": 1,
    }
    monkeypatch.setattr(provider, "_connect", lambda: _FakeConnection(feature_collection))

    transformed = provider.query(crs_transform_spec=create_crs_transform_spec(provider_def=provider_def))

    coordinates = transformed["features"][0]["geometry"]["coordinates"][0][0]
    expected_lon, expected_lat = pyproj.Transformer.from_crs(5972, 4326, always_xy=True).transform(
        526131.4498, 6849490.719999999
    )
    assert isclose(coordinates[0], expected_lon, rel_tol=0, abs_tol=1e-6)
    assert isclose(coordinates[1], expected_lat, rel_tol=0, abs_tol=1e-6)
    assert coordinates[2] == 402.2