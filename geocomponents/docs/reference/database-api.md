# Public database API

geocomponents creates the `ogc.*` PostgreSQL functions for reading and writing data when applying dataset descriptions.
Call them with the dataset and collection names from those descriptions to read or write GeoJSON features.
Callers do not need to know which tables or generated functions store the features.

## Read features

| Function | Arguments | Operation | Returns |
| --- | --- | --- | --- |
| `ogc.feature_items` | `dataset text, collection text, bbox float8[] = NULL, lim int = 10, off int = 0, with_matched boolean = true` | List features in a collection, optionally filtering by bounding box and paginating with limit and offset. | `jsonb` GeoJSON FeatureCollection |
| `ogc.feature_item` | `dataset text, collection text, fid uuid` | Get a feature by its ID. | `jsonb` GeoJSON Feature, or `NULL` if absent |

## Write features

| Function | Arguments | Operation | Returns |
| --- | --- | --- | --- |
| `ogc.feature_create` | `dataset text, collection text, feature jsonb` | Add a feature to a collection. | `uuid` of the created feature |
| `ogc.feature_replace` | `dataset text, collection text, fid uuid, feature jsonb` | Replace a feature's content by ID. | `boolean`: whether the feature was found and replaced |
| `ogc.feature_update` | `dataset text, collection text, fid uuid, feature jsonb` | Update only fields supplied in the feature. | `boolean`: whether the feature was found and updated |
| `ogc.feature_delete` | `dataset text, collection text, fid uuid` | Remove a feature by ID. | `boolean`: whether the feature was found and deleted |
| `ogc.feature_upsert` | `dataset text, collection text, feature jsonb` | Insert a feature or replace the one matching its upsert identifier. | Stable `uuid` of the stored feature |

`feature_create`, `feature_replace`, `feature_update`, and `feature_delete` are single-feature operations for collections with `feature_model: simple` (the default).
`feature_create` does not require an identifier: it generates a UUID when none is supplied.
OGC API Features Part 4 permits a server to either use or ignore an ID supplied in a POST create body.
`feature_create` allows a user to supply an id by accepting a supplied GeoJSON `id` (or an `outward_identifier` value) as the new row ID; if both are supplied, they must match.
For HTTP PUT, the resource ID comes from the URL, `feature_replace` receives that ID separately as `fid`.

`feature_upsert` needs an identifier to match an existing feature.
It uses the collection's `outward_identifier` field when declared, or a top-level `lokalid` field when present.
Without either field, upsert is unavailable.
The `lokalid` fallback is current behavior and is [planned for removal](https://github.com/kartverket/topografisk-gdb-api/issues/134); it is not an explicit upsert setting.
`feature_upsert` is a project-specific operation, not a Part 4 upsert rule.
In particular, it does not implement PUT at a feature URL, which identifies the target by its URL.

Direct writes to `feature_model: topology` collections are rejected.

## Transactions

`ogc.transaction(dataset text, document jsonb)` applies changes across multiple features, necessary for topology updates.
See [transactions](./transactions.md) for the current atomic document and report format.
