"""Description-driven geographic components: a folder of YAML descriptions
becomes a PostGIS database (``schema/``) and a composite OGC API service
(``api/`` mounted by ``gateway/``).

Database and API communicate through the ``ogc.feature_*`` functions — see
the *DB ↔ API contract* section in the README.
"""
