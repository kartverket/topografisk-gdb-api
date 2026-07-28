"""Registry mapping process ids (declared in ``DatasetDef.processes``) to
pygeoapi processor classes, plus a placeholder processor. Real processes
will be backed by generated DB functions in the future — same dispatch
pattern as features, likely under ``ogc.processes_*``.
"""
