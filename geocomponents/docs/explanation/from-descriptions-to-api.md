# From descriptions to database and API

geocomponents uses dataset descriptions to define both the stored data and the API that exposes it.
A dataset is represented by a PostgreSQL schema and an OGC API mounted at `/datasets/<name>/ogc_api`; its collections become tables and API collections.
This keeps the names and shapes on both sides tied to the same description.

## Constructing the database and API

Two commands are used to construct the database and API:

- `apply-schema` loads the descriptions and builds the database structures: tables, indexes, and functions for each dataset.
- `serve` loads the descriptions again and mounts an API for each dataset.

The API reads and writes features through database functions rather than constructing its own storage model.

The responsibilities are split across four components:

- `descriptions/` loads and resolves the dataset definitions.
- `schema/` turns resolved definitions into PostGIS tables and functions.
- `api/` builds an OGC API for one dataset.
- `gateway/` mounts the dataset APIs into one service and lists them at `/datasets`.

## The database and API boundary

The API uses the public `ogc.*` database functions with dataset and collection names from the descriptions.
For example, a request for a feature in the `my_collection` collection of `my_dataset` is routed through the corresponding database function rather than accessing the `my_collection` table directly.
The database handles feature storage and validation; the API exposes it using OGC routes, links, and paging.

## Changes to descriptions

Both stages must use the intended version of the description.
Applying the schema creates missing structures, such as a new collection, but does not migrate existing tables or columns when their definitions change.
Those changes need a manual database migration; re-running `apply-schema` alone is not enough.
