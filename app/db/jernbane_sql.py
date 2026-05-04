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
