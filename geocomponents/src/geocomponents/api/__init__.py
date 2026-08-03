"""Serve a ``ResolvedDataset`` as an OGC API — Features application.

Defines the ``DatasetApiProvider`` protocol (the gateway's seam) and ships a
pygeoapi implementation that reads and writes through the ``ogc.feature_*``
functions expected in the database (see ``schema/``).
"""
