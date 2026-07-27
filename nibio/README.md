# NIBIO AR5 database

Reference material from NIBIO's AR5 topology database, kept for upcoming topology integration.

- `ar5_nibio_db_init.sql` — dump of the NIBIO AR5 database (schema + sample data). Geometry SRID is 4258 (ETRS89).
- `alter_nibio_schema.sql` — local adjustments applied on top of the dump: enum-like smallint columns (e.g. `arealtype`) converted to text, with dependent views recreated. NIBIO's topology functions may assume the original smallint types — re-verify when integrating.
- `nibio_appconfig.json` — NIBIO's application configuration: the authoritative lists of face/edge attribute columns, plus topology and operations settings.
