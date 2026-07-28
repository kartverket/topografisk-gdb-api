"""Turn a ``ResolvedDataset`` into a PostGIS database: a PostgreSQL schema of
tables plus the ``ogc.feature_*`` dispatch functions the API calls:

  * ``ogc.feature_items``   — list features (paged, optional bbox)
  * ``ogc.feature_item``    — read one feature
  * ``ogc.feature_create``  — insert a feature
  * ``ogc.feature_replace`` — replace a feature (PUT semantics)
  * ``ogc.feature_update``  — patch a feature (only fields present change)
  * ``ogc.feature_delete``  — delete a feature

See the *DB ↔ API contract* section in the README.
"""
