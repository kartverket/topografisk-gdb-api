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
> `arealressurs_flate`).

### A collection

A **collection** is one feature type (for example, parcels). Each becomes a table
and an API collection:

```yaml
collections:
  - name: parcels               # required — the table + collection name
    title: Parcels
    description: Land parcels.
    feature_model: simple       # 'simple' (default) = read + edit
                                # 'topology'         = write through ogc.transaction
    geometry:
      type: MultiPolygon        # shape type (see the list below)
      srid: 4326                # coordinate system (default 4326 = WGS84)
    fields:                     # your attributes (see below)
      - name: label
        type: string
        required: true
```

- **`feature_model`** — `simple` collections use the single-feature entrypoints
  (`ogc.feature_create`, `ogc.feature_update`, `ogc.feature_replace`,
  `ogc.feature_delete`). `topology` collections take part in link and boundary
  validation, so their writes go through `ogc.transaction`. Direct
  `ogc.feature_*` writes are rejected for those collections, and the HTTP OGC
  item-write endpoints therefore remain unavailable for them.
- **`geometry`** — the shape type and coordinate system. The type is enforced
  exactly: a `MultiPolygon` column rejects a plain `Polygon`. Set `has_z: true`
  when coordinates include height; PostGIS then uses the `*Z` typmod
  (e.g. `LineStringZ`).

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
| `object` | jsonb (nested object — see below) |

Set `indexable: true` on any scalar field to add a database index. On an
`object` field, `indexable: true` on a sub-field adds a functional index on
that key inside the JSONB column.

#### Nested objects

A field with `type: object` stores a JSON object (JSONB column). Its shape is
declared with a nested `fields` list; sub-fields follow the same typing rules,
including `codelist` references:

```yaml
- name: kvalitet
  type: object
  required: true
  fields:
    - name: datafangstmetode
      codelist: datafangstmetode
      required: true
    - name: noyaktighet
      type: integer
    - name: synbarhet
      codelist: synbarhet
      indexable: true   # adds a functional index on (kvalitet->>'synbarhet')
```

### Relationships

A relationship links a collection to another collection **in the same dataset**.
Links are declared with a source-side `property` name and a `target`
collection:

```yaml
collections:
  - name: buildings
    geometry: { type: MultiPolygon, srid: 4326 }
    relationships:
      - property: parcel
        target: parcels
```

geocomponents stores links in one association table per dataset instead of
adding `<property>_id` columns to feature tables:

- `<dataset>.association` holds the actual rows: source collection, source id,
  property, target collection, target id.
- `<dataset>.association_role` is the generated catalogue of declared
  `property -> target` pairs. Writes are checked against it, so an undeclared
  property is not writable.

On the wire, a relationship property is always an array of link elements. Each
element carries `featuretype` plus the target collection's identifier key:
`id`, or the leaf of its `outward_identifier` path when it declares one.

This is a real transaction item written to a topology collection:

```json
{
  "action": "insert",
  "collection": "surface",
  "feature": {
    "type": "Feature",
    "id": "e50d34e9-65bd-442c-9bb1-9884d9d065fc",
    "geometry": {
      "type": "MultiPolygon",
      "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]]
    },
    "properties": {
      "boundedByOuter": [
        {
          "featuretype": "border1",
          "lokalid": "153394d7-c0ef-4444-9c7f-d0f38801a17a"
        }
      ],
      "boundedByShared": [
        {
          "featuretype": "border2",
          "lokalid": "9e9ba4b7-0a33-4738-abc3-493d89c14894"
        }
      ]
    }
  }
}
```

Read back through `ogc.feature_item`, the same feature looks like this:

```json
{
  "id": "e50d34e9-65bd-442c-9bb1-9884d9d065fc",
  "type": "Feature",
  "geometry": {
    "type": "MultiPolygon",
    "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]]
  },
  "properties": {
    "created_at": "2026-08-31T14:33:49.842254+00:00",
    "updated_at": "2026-08-31T14:33:49.842254+00:00",
    "boundedByOuter": [
      {
        "lokalid": "153394d7-c0ef-4444-9c7f-d0f38801a17a",
        "featuretype": "border1"
      }
    ],
    "boundedByShared": [
      {
        "lokalid": "9e9ba4b7-0a33-4738-abc3-493d89c14894",
        "featuretype": "border2"
      }
    ]
  }
}
```

Link writes for `feature_model: topology` collections go through
`ogc.transaction`. A direct single-feature write such as
`ogc.feature_create('cadastre', 'blocks', ...)` is rejected with
`P0001: collection blocks does not support direct write operations`.

### Fixed columns

Every collection has these without declaring them in `fields:`:

- `id` — UUID primary key, generated by the server
- `geometry` — the shape column; its type, SRID and Z flag come from the collection's `geometry:` key
- `created_at`, `updated_at` — write timestamps, maintained automatically

In API responses (GeoJSON), `id` and `geometry` are top-level; your attributes
plus `created_at`/`updated_at` appear under `properties`.

### Server-managed fields

Two collection keys hand ownership of field values to the server. Client-supplied
values for these fields are stripped on write and replaced by the server.

**`outward_identifier`** makes a field path the feature's identifier on the
wire. The path's leaf value is the row id: the client may supply it on insert,
it is fixed afterwards, and the server projects it back on read:

```yaml
outward_identifier: identifikasjon.lokalid
```

For example, a feature created with id
`00000000-0000-0000-0000-00000000000a` is read back as:

```json
{
  "id": "00000000-0000-0000-0000-00000000000a",
  "type": "Feature",
  "geometry": {
    "type": "LineString",
    "coordinates": [[10, 55], [11, 56]]
  },
  "properties": {
    "created_at": "2026-08-31T14:34:26.672522+00:00",
    "updated_at": "2026-08-31T14:34:26.672522+00:00",
    "identification": {
      "testoi": "00000000-0000-0000-0000-00000000000a"
    }
  }
}
```

**`server_managed`** — a map of paths to tokens:

| token | behaviour |
|---|---|
| `timestamp_iso` | set to `now()` on every write; client value discarded |
| `outward_identifier` | same as the top-level `outward_identifier:` key |

```yaml
server_managed:
  identifikasjon.versjonid: timestamp_iso   # sub-field inside the identifikasjon JSONB column
  oppdateringsdato: timestamp_iso           # top-level scalar column
```

A path with two segments (`identifikasjon.versjonid`) targets a key inside a
JSONB column. A single-segment path (`oppdateringsdato`) targets a top-level
scalar column.

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

Codelists can also be declared directly in a dataset file under a top-level
`codelists:` key — dataset-local codelists take precedence over commons ones
with the same name. Fields that use a codelist are validated at the database
level: an invalid code value returns HTTP 422.

### Geometry types

`Point`, `MultiPoint`, `LineString`, `MultiLineString`, `Polygon`,
`MultiPolygon`, `GeometryCollection`. `srid` defaults to `4326` (WGS84
longitude/latitude). If you omit `geometry`, it defaults to a `Point`.
Optional `has_z: true` stores XYZ coordinates (PostGIS `PointZ`,
`LineStringZ`, …).

Collections can also declare that their geometry is derived from linked member
features. Today the available rule is `footprint`, which builds a surface from
linked linework:

```yaml
geometry:
  type: MultiPolygon
  srid: 4326
  required: false
  derived:
    rule: footprint
    areas: many
    holes: forbidden
    one_of:
      - [boundedByOuter]
      - [{name: boundedByConditional, when: is_bounding}]
```

- `rule: footprint` means the collection's boundary is read from linked member
  geometries.
- `areas` is required for `footprint`: `one` rejects
  `multiple_disjoint_areas`; `many` accepts them.
- `holes` is required for `footprint`: `forbidden` rejects
  `holes_not_allowed`; `allowed` accepts them.
- `one_of` lists the allowed role alternatives for the boundary members.
- `when` on a role names a boolean field on the target feature. That role is
  included only when the field is true.

`feature_model: topology` and `derived:` are separate declarations. A topology
collection may use direct geometry writes, derived geometry, or both, depending
on what the description says today.

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

The [shared descriptions folder](../descriptions/) is a complete, runnable example:
`cadastre.yaml` (a `parcels` collection using a code list and a shared type, a
`buildings` collection with a relationship, and a `blocks` topology
collection), `hydro.yaml`, `fkb_bane.yaml`, `bygning.yaml`, and a shared
`commons.yaml`.

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
communicate. The database delivers a fixed `ogc.*` surface which callers use
with OGC identifiers (`dataset`, `collection`) rather than physical table or
function names. Single-feature reads and writes go through `ogc.feature_*`;
atomic multi-feature writes go through `ogc.transaction`. The functions follow
the naming and formatting expected by the OGC standards. The API uses these
functions to read and write features, which makes either database or API
substitutable as long as they adhere to the same contract.

**The public ogc.* contract:**

| Surface                              | Function              | Arguments                                                                  | Returns                                                                  |
| ------------------------------------ | --------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `GET /collections/{c}/items`         | `ogc.feature_items`   | `dataset, collection, bbox float8[], lim int, off int, with_matched bool` | `jsonb` — a GeoJSON `FeatureCollection`                                  |
| `GET /collections/{c}/items/{id}`    | `ogc.feature_item`    | `dataset, collection, fid uuid`                                            | `jsonb` — a `Feature`, or null if the id is absent                       |
| `POST /collections/{c}/items`        | `ogc.feature_create`  | `dataset, collection, feature jsonb`                                       | `uuid` of the new feature                                                |
| `PUT /collections/{c}/items/{id}`    | `ogc.feature_replace` | `dataset, collection, fid uuid, feature jsonb`                             | `boolean` — true when a matching feature was replaced                    |
| `PATCH /collections/{c}/items/{id}`  | `ogc.feature_update`  | `dataset, collection, fid uuid, feature jsonb`                             | `boolean` — true when updated; only fields present in the input change   |
| `DELETE /collections/{c}/items/{id}` | `ogc.feature_delete`  | `dataset, collection, fid uuid`                                            | `boolean` — true when a matching feature was deleted                     |
| `POST /collections/{c}/items:upsert` | `ogc.feature_upsert`  | `dataset, collection, feature jsonb`                                       | stable `uuid`; available when the collection resolves an upsert key      |
| Atomic multi-feature write           | `ogc.transaction`     | `dataset, document jsonb`                                                  | `jsonb` — a fixed-shape transaction report                               |

Endpoints are relative to a dataset mount, e.g.
`/datasets/cadastre/ogc_api/collections/parcels/items`.
The `ogc.transaction` row is a database-contract entrypoint today; it is not
yet routed from an HTTP transaction endpoint in this repo.

The `dataset` and `collection` arguments come from the description
(`cadastre`, `parcels`) — the same names OGC puts in the URL. The dispatcher
routes `ogc.feature_items('cadastre', 'parcels', …)` to a per-collection
function `cadastre._parcels_items(…)` generated from the description.
`ogc.transaction('cadastre', …)` routes item actions the same way, to the
generated `cadastre._<collection>_<op>` functions. Change the storage layout,
update the dispatcher; callers keep using the same `ogc.*` surface.
Collections with a resolved upsert key also receive a unique index and an
atomic insert-or-replace function keyed by that field. The key comes from
`outward_identifier`, or defaults to `lokalid` when present.

Direct `ogc.feature_*` writes are for simple-feature collections. They consult
per-dataset capability metadata and refuse `feature_model: topology`
collections; `ogc.transaction` is the write path for those collections.
Client-supplied feature ids are honored when the generated write function for a
collection accepts them.

**Transaction document shape**

`ogc.transaction` accepts atomic documents of this form:

```json
{
  "semantic": "atomic",
  "transaction": [
    {
      "action": "insert",
      "collection": "parcels",
      "feature": {
        "type": "Feature",
        "id": "…",
        "geometry": {"type": "MultiPolygon", "coordinates": [[[[10, 55], [10, 56], [11, 56], [11, 55], [10, 55]]]]},
        "properties": {"label": "P-1"}
      }
    },
    {
      "action": "update",
      "collection": "parcels",
      "id": "…",
      "feature": {"properties": {"label": "updated"}}
    }
  ]
}
```

The verb set is `insert`, `update`, `replace`, `delete`. `upsert` is not part
of the transaction document.

**Transaction report shape**

`ogc.transaction` returns a fixed-shape report:

```json
{
  "committed": false,
  "phase": "items",
  "reason": null,
  "sqlstate": null,
  "items": [
    {
      "index": 1,
      "action": "update",
      "collection": "parcels",
      "id": null,
      "status": "rejected",
      "sqlstate": "P0001",
      "reason": "invalid geometry"
    }
  ],
  "structure": [],
  "geometry": []
}
```

`phase` is `document`, `items`, `structure`, or `geometry`.

- `document` means the transaction document itself was rejected before any item
  ran.
- `items` means an item failed while the transaction was applying the document.
- `structure` means the document applied, then the structural validation pass
  found problems.
- `geometry` means the structural pass was clean and the geometry pass found
  problems.

`reason` is the top-level failure message when a pass raises. It is `null` on
committed reports, item rejections, and findings reports. Top-level `sqlstate`
is always present: it is the Postgres error code when a pass raises, and `null`
otherwise. Under atomic semantics, an item-level failure reports only the
rejected item, because no earlier change is visible after the rollback.

`structure` and `geometry` are always-present arrays. Each pass either leaves
its array empty or fills it with findings from that pass.

This is a document-level failure from a real call:

```json
{
  "items": [],
  "phase": "document",
  "reason": "unsupported semantic: bogus",
  "geometry": [],
  "sqlstate": "P0001",
  "committed": false,
  "structure": []
}
```

This is a structural findings report:

```json
{
  "items": [],
  "phase": "structure",
  "reason": null,
  "geometry": [],
  "sqlstate": null,
  "committed": false,
  "structure": [
    {
      "id": "870a1fad-3b9f-4de5-b2af-2b2cb19eb372",
      "rule": "footprint",
      "valid": false,
      "reason": "conflicting_boundary_roles",
      "details": {
        "roles": ["boundedByConditional", "boundedByOuter"]
      },
      "members": 2,
      "included": 2,
      "collection": "surface"
    }
  ]
}
```

This is a geometry findings report:

```json
{
  "items": [],
  "phase": "geometry",
  "reason": null,
  "geometry": [
    {
      "id": "22a57c6c-86ad-4372-be32-5f3063e319a0",
      "rule": "footprint",
      "areas": 1,
      "holes": 0,
      "valid": false,
      "reason": "unused_boundary_line",
      "details": {
        "unused": [
          {
            "id": "1ce4f64d-41ff-4a96-bcb5-c724e420f5b6",
            "collection": "border1"
          }
        ]
      },
      "members": 2,
      "included": 2,
      "collection": "surface2"
    }
  ],
  "sqlstate": null,
  "committed": false,
  "structure": []
}
```

The structural finding reasons are `missing_member`,
`conflicting_boundary_roles`, and `no_boundary`. The geometry finding reasons
are `nonsimple_boundary`, `boundary_does_not_close`, `unused_boundary_line`,
`multiple_disjoint_areas`, and `holes_not_allowed`.

You can call them directly:

```sql
select ogc.feature_items('cadastre', 'parcels', null, 10, 0, true);
select ogc.feature_item('cadastre', 'parcels', '…uuid…');
select ogc.transaction(
    'cadastre',
    '{
      "semantic": "atomic",
      "transaction": [
        {
          "action": "insert",
          "collection": "parcels",
          "feature": {
            "type": "Feature",
            "id": "…uuid…",
            "geometry": {"type": "MultiPolygon", "coordinates": [[[[10,55],[10,56],[11,56],[11,55],[10,55]]]]},
            "properties": {"label": "P-1"}
          }
        }
      ]
    }'::jsonb
);
```

### Not built yet
- Importing descriptions from GML/UML models.
- Emitting events when data changes.
- Migrations when a description changes an existing table. Until then, operators
  must migrate manually — see the note in [DEPLOY.md](DEPLOY.md#extra-development-note).
