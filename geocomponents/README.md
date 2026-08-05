# geocomponents

**geocomponents turns a plain description of your geographic data into a working
database and web API.** You describe your data once in YAML; it creates the
PostGIS tables and a standards-based (OGC) web API to read and edit that data —
no SQL or API code to write by hand. Change the description, re-run, and the
database and API follow.

## How it works

You write a **description** (YAML) → run geocomponents → for each dataset you get:

- a **PostGIS database** — one schema of tables, and
- a **web API** at `/datasets/<name>/ogc_api` to read and edit the data
  (an [OGC API — Features](https://ogcapi.ogc.org/features/) service).

The description is the single source of truth: the database and the API are both
generated from it.

## Describing a dataset

A description is a **folder of YAML files**. Each file is one *dataset*; an
optional `commons.yaml` holds definitions shared by all of them. Point
geocomponents at the folder with the `GEOCOMPONENTS_DESCRIPTIONS` setting.

### A dataset

```yaml
name: cadastre           # required — becomes the DB schema and the API path
title: Cadastre          # optional — a human-friendly name
description: Land registry data.   # optional
processes:               # optional — named operations to expose (see below)
  - hello
collections:             # the feature types in this dataset
  - ...
```

`name` becomes the PostgreSQL schema and the API mount path, e.g.
`/datasets/cadastre/ogc_api`.

> **Naming:** dataset and collection `name`s become raw SQL
> identifiers, so use **lowercase** letters, digits and underscores only — no
> hyphens (`fkb-bane` → `fkb_bane`) and no uppercase (`arealressursFlate` →
> `arealressurs_flate`). This restriction will be lifted later.

### A collection

A **collection** is one feature type (for example, parcels). Each becomes a table
and an API collection:

```yaml
collections:
  - name: parcels               # required — the table + collection name
    title: Parcels
    description: Land parcels.
    feature_model: simple       # 'simple' (default) = read + edit
                                # 'topology'         = read-only
    geometry:
      type: MultiPolygon        # shape type (see the list below)
      srid: 4326                # coordinate system (default 4326 = WGS84)
    fields:                     # your attributes (see below)
      - name: label
        type: string
        required: true
```

- **`feature_model`** — `simple` collections can be read *and* edited
  (create/update/delete). `topology` collections share geometry between
  neighbouring features, so they are **read-only** for now; edit requests return
  `405 Method Not Allowed`.
- **`geometry`** — the shape type and coordinate system. The type is enforced
  exactly: a `MultiPolygon` column rejects a plain `Polygon`.

### Fields (attributes)

Each field is one attribute (one column). Give it a `name` and **exactly one** way
to type it — a builtin `type`, a `type_ref` (a reusable type from `commons.yaml`),
or a `codelist` (a controlled vocabulary from `commons.yaml`):

```yaml
fields:
  - name: label
    type: string          # a builtin type (table below)
    required: true        # optional, default false

  - name: municipality
    type_ref: municipality_code   # a named type defined in commons.yaml

  - name: status
    codelist: parcel_status       # a code list defined in commons.yaml
```

Builtin `type` values:

| `type` | stored as |
|---|---|
| `string` | text |
| `integer` | integer |
| `number` | double precision |
| `boolean` | boolean |
| `date` | date |
| `timestamp` | timestamp (with time zone) |
| `uuid` | uuid |

### Relationships

A relationship links a collection to another collection **in the same dataset**.
It adds a `<name>_id` column that points at the target:

```yaml
collections:
  - name: buildings
    geometry: { type: MultiPolygon, srid: 4326 }
    relationships:
      - name: parcel        # adds a 'parcel_id' column
        target: parcels     # referencing the 'parcels' collection
```

### Columns you get for free

Every collection automatically gets these — **do not declare them yourself**:

- `id` — a unique identifier, generated for you (UUID)
- `geometry` — the shape, typed as you specified
- `created_at`, `updated_at` — timestamps, maintained for you

In API responses (GeoJSON), `id` and `geometry` are top-level; your attributes
plus `created_at`/`updated_at` appear under `properties`.

### Shared definitions — `commons.yaml`

An optional `commons.yaml` in the folder holds definitions every collection
inherits:

```yaml
base_fields:              # extra attributes added to EVERY collection
  - name: source
    type: string
    description: Where the feature came from.

field_types:              # reusable named types, used via `type_ref`
  - name: municipality_code
    sql_type: varchar(4)

code_lists:               # controlled vocabularies, used via `codelist`
  - name: parcel_status
    values:
      - { code: active, label: Active }
      - { code: retired, label: Retired }
```

### Geometry types

`Point`, `MultiPoint`, `LineString`, `MultiLineString`, `Polygon`,
`MultiPolygon`, `GeometryCollection`. `srid` defaults to `4326` (WGS84
longitude/latitude). If you omit `geometry`, it defaults to a `Point`.

### Processes

`processes` lists named operations (OGC API — Processes) the dataset exposes at
`/processes/<id>`. Each id must be registered in the process registry
(`src/geocomponents/processes/registry.py`); the example ships a `hello` process.

### A minimal dataset

The smallest useful dataset — a name and one collection with a geometry and a
field:

```yaml
name: places
collections:
  - name: points_of_interest
    geometry:
      type: Point
    fields:
      - name: name
        type: string
        required: true
```

### A working example

The [`descriptions/`](descriptions/) folder is a complete, runnable example:
`cadastre.yaml` (a `parcels` collection using a code list and a shared type, a
`buildings` collection with a relationship, and a read-only `blocks` topology
collection), a shared `commons.yaml`, and a second dataset `hydro.yaml`.

## Running it (local)

The whole stack runs in Docker Compose. The app reads the **same discrete `DB_*`
variables** used in production (no special local config path), and your `src/` is
mounted into the container so code edits take effect on a restart — no rebuild:

```bash
docker compose up --build
# db  →  migrate (geocomponents apply-schema)  →  api (geocomponents serve) on :8000
```

`docker compose up db` brings up just PostGIS (used by the host-run tests below).
The image's entrypoint is the `geocomponents` CLI (`validate` | `apply-schema` |
`serve`); the compose services simply run those subcommands.

## Using the API

```bash
# List datasets, then one dataset's collections and features
curl localhost:8000/datasets
curl "localhost:8000/datasets/cadastre/ogc_api/collections/parcels/items?f=json"

# Create a feature (simple collections only)
curl -X POST localhost:8000/datasets/cadastre/ogc_api/collections/parcels/items \
  -H 'content-type: application/geo+json' \
  -d '{"type":"Feature","geometry":{"type":"MultiPolygon","coordinates":[[[[10,55],[10,56],[11,56],[11,55],[10,55]]]]},"properties":{"label":"P1","source":"demo"}}'

# Run a process
curl -X POST localhost:8000/datasets/cadastre/ogc_api/processes/hello/execution \
  -H 'content-type: application/json' -d '{"inputs":{"name":"world"}}'
```

Open `http://localhost:8000/datasets/cadastre/ogc_api/` in a browser for the
built-in HTML view.

## Testing

```bash
docker compose up -d db      # PostGIS on localhost:55432
uv run pytest                # unit tests run without Docker; DB-backed
                             # contract/integration tests use the database above
```

The suite is written as an executable **contract**: it drives the components at
their real surfaces (the `ogc.feature_*` database functions and the HTTP OGC API),
so a reimplementation in another language would pass the same tests.

## Deployment

geocomponents ships as a container image (engine only — descriptions are supplied
at runtime, not baked in) and is deployed to Kubernetes + CloudSQL by a separate
apps repo. See **[DEPLOY.md](DEPLOY.md)** for the operational contract: the `DB_*`
connection variables and `GEOCOMPONENTS_*` settings, the *apply-schema then serve*
lifecycle, and the `/healthz` (liveness) + `/datasets` (readiness) probes.

## How it's built

Each dataset becomes one PostgreSQL schema; each collection becomes one
table. The database shapes the data and handles create/read/update/delete;
the API adds the OGC links and paging on top. They meet at the `ogc.feature_*`
functions — see the *DB ↔ API contract* subsection below.

The four parts are independently swappable: **`descriptions/`** (the format +
loader), **`schema/`** (description → PostGIS tables + functions), **`api/`** (one
dataset → one OGC API app), and **`gateway/`** (many apps → one service).

### The DB ↔ API contract

The database and the API share a **standard-shaped surface** for how they
communicate. The database delivers functions in the format `ogc.feature_*`
which the API calls. The functions follow naming and formatting expected by
the OGC standards. The API uses these functions to read and write features
which makes either database or API substitutable as long as they adhere to
the same contract.

Note that writing is currently only supported for simple features. In the
future, processes and atomic transactions will be added for topological
features following the same design: named functions in the database exposed
for the API.

**The six core functions, plus optional business-key upsert:**

| Endpoint (per collection)            | Function              | Arguments                                                                | Returns                                                                 |
| ------------------------------------ | --------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| `GET /collections/{c}/items`         | `ogc.feature_items`   | `dataset, collection, bbox float8[], lim int, off int, with_matched bool` | `jsonb` — a GeoJSON `FeatureCollection`                                 |
| `GET /collections/{c}/items/{id}`    | `ogc.feature_item`    | `dataset, collection, fid uuid`                                          | `jsonb` — a `Feature`, or null if the id is absent                      |
| `POST /collections/{c}/items`        | `ogc.feature_create`  | `dataset, collection, feature jsonb`                                     | `uuid` of the new feature                                               |
| `PUT /collections/{c}/items/{id}`    | `ogc.feature_replace` | `dataset, collection, fid uuid, feature jsonb`                           | `boolean` — true when a matching feature was replaced                   |
| `PATCH /collections/{c}/items/{id}`  | `ogc.feature_update`  | `dataset, collection, fid uuid, feature jsonb`                           | `boolean` — true when updated; only fields present in the input change  |
| `DELETE /collections/{c}/items/{id}` | `ogc.feature_delete`  | `dataset, collection, fid uuid`                                          | `boolean` — true when a matching feature was deleted                    |
| `POST /collections/{c}/items:upsert` | `ogc.feature_upsert` | `dataset, collection, feature jsonb` | stable `uuid`; available when the collection declares `upsert_key` |

Endpoints are relative to a dataset mount, e.g.
`/datasets/cadastre/ogc_api/collections/parcels/items`.

The `dataset` and `collection` arguments come from the description
(`cadastre`, `parcels`) — the same names OGC puts in the URL. The dispatcher
routes `ogc.feature_items('cadastre', 'parcels', …)` to a per-collection
function `cadastre._parcels_items(…)` generated from the description. Change
the storage layout, update the dispatcher; the API keeps calling the same
functions. Collections with an `upsert_key` also receive a unique index and an
atomic insert-or-replace function keyed by those fields.

You can call them directly:

```sql
select ogc.feature_items('cadastre', 'parcels', null, 10, 0, true);
select ogc.feature_item('cadastre', 'parcels', '…uuid…');
```

### Not built yet (designed for)
- Importing descriptions from GML/UML models.
- Emitting events when data changes.
- Enforcing validation (types, code lists, SRID) in the database.
- Migrations when a description changes an existing table. Until then, operators
  must migrate manually — see the note in [DEPLOY.md](DEPLOY.md#extra-development-note).
