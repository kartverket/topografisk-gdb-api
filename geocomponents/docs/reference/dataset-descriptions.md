# Dataset descriptions

Set `GEOCOMPONENTS_DESCRIPTIONS` to a directory of YAML files.
Each `*.yaml` file defines one dataset.

| Key | Type | Accepted values | Required / default | Meaning |
| --- | --- | --- | --- | --- |
| `name` | string | [Dataset name](./dataset-and-collection-names.md) | Required | Identifier naming the PostgreSQL schema and the API mount at `/datasets/<name>/ogc_api`. |
| `srid` | integer | Spatial reference identifier | Required | Coordinate reference system shared by all geometries in the dataset. |
| `title` | string | Any string | Optional; no default | Human-readable dataset title. |
| `description` | string | Any string | Optional; no default | Human-readable dataset description. |
| `processes` | list of strings | [Registered process IDs](./process-descriptions.md) | Optional; empty list | Processes to expose for the dataset. |
| `collections` | list | [Collection descriptions](./collection-descriptions.md) | Optional; empty list | Feature types belonging to this dataset. |
| `codelists` | list | Code lists with a `name` and a list of `values` (each with a `code` and optional `label`) | Optional; empty list | Named allowed values referenced by a field's `codelist`. |
