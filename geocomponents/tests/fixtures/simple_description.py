"""Fresh expected description for the simple-feature test fixture."""


def expected_simple_description() -> dict:
    return {
        "name": "EksempelDatasett",
        "title": "Example simple features",
        "description": "Simple features with and without a projected identifier.",
        "processes": ["upsert-batch"],
        "collections": [
            {
                "name": "with_oi",
                "title": "With OI",
                "description": "",
                "geometry": {"type": "LineString", "srid": 4326},
                "outward_identifier": "identification.testoi",
                "fields": [
                    {"name": "label", "type": "string", "max_length": 4},
                    {
                        "name": "identification",
                        "type": "object",
                        "required": True,
                        "fields": [{"name": "testoi", "type": "string"}],
                    },
                ],
            },
            {
                "name": "NårwegiænØbject",
                "title": "Example object",
                "description": "Simple feature with norwegian letters and camelCase",
                "geometry": {"type": "LineString", "srid": 4326},
                "fields": [
                    {"name": "feltØ", "type": "string", "indexable": True},
                    {
                        "name": "egenskaper",
                        "type": "object",
                        "fields": [
                            {"name": "verdiÅ", "type": "integer", "indexable": True}
                        ],
                    },
                ],
            },
        ],
    }
