# Dataset descriptions

Set `GEOCOMPONENTS_DESCRIPTIONS` to a directory of YAML files.
Each `*.yaml` file except `commons.yaml` defines one dataset.
The optional `commons.yaml` contains [definitions shared across datasets](./shared-definitions.md).

| Key | Type | Accepted values | Required / default | Meaning |
| --- | --- | --- | --- | --- |
| `name` | string | [Dataset name](./dataset-and-collection-names.md) | Required | Identifier naming the PostgreSQL schema and the API mount at `/datasets/<name>/ogc_api`. |
| `title` | string | Any string | Optional; no default | Human-readable dataset title. |
| `description` | string | Any string | Optional; no default | Human-readable dataset description. |
| `processes` | list of strings | [Registered process IDs](./process-descriptions.md) | Optional; empty list | Processes to expose for the dataset. |
| `collections` | list | [Collection descriptions](./collection-descriptions.md) | Optional; empty list | Feature types belonging to this dataset. |
| `codelists` | list | [Code lists](./shared-definitions.md#code-lists) | Optional; empty list | Dataset-local lists override shared lists of the same name. |

[Issue #139](https://github.com/kartverket/topografisk-gdb-api/issues/139) proposes removing the support shared definitions from `commons.yaml`.
