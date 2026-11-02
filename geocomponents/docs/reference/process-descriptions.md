# Process descriptions

The dataset-level `processes` key lists processes to expose in that dataset's OGC API.
It is a list of strings containing IDs from the process registry defined at `src/geocomponents/processes/registry.py`.
An ID not in the registry causes description loading to fail.

Processes listed by the dataset are exposed according to [OGC API - Processes](https://ogcapi.ogc.org/processes/) under the dataset's root URL, `/datasets/<name>/ogc_api/`.

## Current processes

| Registered ID | Purpose |
| --- | --- |
| `hello` | Example process. |
| `upsert-batch` | Batch upsert process for collections that support upsert. |
| `import` | Import process backed by an external service. |
