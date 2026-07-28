"""Mount per-dataset OGC API apps under ``/datasets/<name>/ogc_api`` on a
FastAPI service and expose the top-level ``/datasets`` index. Uses the
``DatasetApiProvider`` protocol from ``api/`` to build each dataset's app.
"""
