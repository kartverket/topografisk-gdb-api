# Collection descriptions

Each entry under a dataset's `collections` list describes one feature type.

| Key | Type | Accepted values | Required / default | Meaning |
| --- | --- | --- | --- | --- |
| `name` | string | [Collection name](./dataset-and-collection-names.md) | Required | Identifier used in the dataset's OGC API. |
| `title` | string | Any string | Optional; no default | Human-readable collection title. |
| `description` | string | Any string | Optional; no default | Human-readable collection description. |
| `feature_model` | string | `simple` or `topology` | Optional; `simple` | Determines which write operations are available; direct feature writes are available only for `simple`. |
| `geometry` | object | [Geometry settings](./geometry-descriptions.md) | Optional; required 2D `Point` with SRID 4326 | Shape and coordinate system of features. |
| `fields` | list | [Field descriptions](./field-descriptions.md) | Optional; empty list | Feature attributes. |
| `relationships` | list | [Relationship descriptions](./relationship-descriptions.md) | Optional; empty list | Links to collections in the same dataset. |
| `outward_identifier` | string | [Nested field path](./server-managed-fields.md) | Optional; no default | Projects the feature ID into the named field. |
| `server_managed` | map | [Field paths and tokens](./server-managed-fields.md) | Optional; empty map | Fields whose values are supplied by the server. |
| `bounds` | integer | `1` or `2` | Optional; no default | Number of distinct features that owns a `LineString` or `MultiLineString` collection as a derived boundary. |

## Generated columns

Every collection has these columns without declaring them in `fields`:

| Column | Meaning |
| --- | --- |
| `id` | UUID primary key; generated when no ID is supplied. |
| `geometry` | Shape column with the type, SRID, and Z dimension specified by `geometry`. |
| `created_at`, `updated_at` | Write timestamps maintained by the database. |
