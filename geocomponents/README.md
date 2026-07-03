# geocomponents — description-driven geographic data components

A sketch of components for **storing, distributing and updating geographic data**,
where a neutral **dataset description** is the single source of truth and both the
**database** and the **API** are generated from it — so either can be swapped
without touching the descriptions or each other.

## The idea in one picture

```
descriptions/*.yaml                      ← source of truth (datasets, collections, commons)
        │
        ├── DB SEAM  ───► SchemaPlan ───► PostGIS:
        │                                   • tables                          (schema/postgis.py)
        │                                   • internal _<collection>_<op> fns (schema/functions.py)
        │                                   • fixed ogc.feature_* dispatch    (schema/functions.py)
        │
        └── API SEAM ───► DatasetApiProvider  (api/base.py)
                            └─ pygeoapi impl   (api/pygeoapi_provider.py)
                                 wires each collection to DbFunctionProvider,
                                 which calls ONLY ogc.feature_*(dataset, collection, …)
                                          │
                                          ▼
                                 GATEWAY (gateway/mounter.py)
                            mounts one OGC API per dataset at
                            /datasets/<dataset>/ogc_api  + /datasets index
```

### Two design rules that drive everything
1. **The API never names physical artefacts.** It only ever calls a fixed
   dispatch layer `ogc.feature_items / feature_item / feature_create /
   feature_replace / feature_update / feature_delete`, passing the **OGC
   identifiers** `(dataset, collection)` as arguments. Table names and
   per-collection function names stay inside the database. The contract is *the
   dataset description + OGC*.
2. **The database owns data shaping; the API owns hypermedia.** Generated
   PL/pgSQL functions produce/consume GeoJSON and do the CRUD; pygeoapi adds the
   OGC links / paging envelope (those depend on the mount URL the DB shouldn't
   know).
3. **The description declares capabilities.** Each collection sets a
   `feature_model`: `simple` (OGC Features + Part 4 CRUD) or `topology`
   (shared geometry → reads only for now; writes return **405**, CRUD arrives
   later via processes + Part 11 Transactions). Each dataset declares which
   `processes` to expose. A mixed dataset still declares Part 4 conformance —
   topology collections are simply non-editable.

### Replaceability seams
| Component | Responsibility | Swap by… |
|---|---|---|
| `descriptions/` | meta-schema + loader (source of truth) | — |
| `schema/` | description → `SchemaPlan` → PostGIS tables + functions | new DB adapter on `SchemaPlan` |
| `api/` | one description → one mountable OGC API app | new `DatasetApiProvider` |
| `gateway/` | many apps → one service + dataset index | composition root (no pygeoapi import) |

## Run it (local)

The whole stack runs in Docker Compose. The app services read the **same discrete
`DB_*` variables** used in production (no special local config path), and your
`src/` is mounted into the container so code edits take effect on a restart — no
rebuild:

```bash
docker compose up --build
# db  →  migrate (geocomponents apply-schema)  →  api (geocomponents serve) on :8000
```

`docker compose up db` brings up just PostGIS (used by the host-run tests below).
The image's entrypoint is the `geocomponents` CLI (`validate` | `apply-schema` |
`serve`); the compose services simply run those subcommands.

Then:

```bash
curl localhost:8000/datasets
curl "localhost:8000/datasets/cadastre/ogc_api/collections/parcels/items?f=json"

# Part 4 CRUD
curl -X POST localhost:8000/datasets/cadastre/ogc_api/collections/parcels/items \
  -H 'content-type: application/geo+json' \
  -d '{"type":"Feature","geometry":{"type":"MultiPolygon","coordinates":[[[[10,55],[10,56],[11,56],[11,55],[10,55]]]]},"properties":{"label":"P1","source":"demo"}}'

# Processes
curl -X POST localhost:8000/datasets/cadastre/ogc_api/processes/hello/execution \
  -H 'content-type: application/json' -d '{"inputs":{"name":"world"}}'
```

You can also call the DB directly to prove the database owns the shaping
independently of the API:

```sql
-- with_matched=false omits the (potentially expensive) numberMatched count
select ogc.feature_items('cadastre', 'parcels', null, 10, 0, true);
```

## Tests

Language-agnostic **contract tests** treat the components as black boxes at
their real surfaces, so a reimplementation in another language passes unchanged:

- `tests/test_*.py` — unit tests for loader/build/functions/config (**no DB**).
- `tests/contract/test_db_contract.py` — the DB contract: calls only
  `ogc.feature_*` (SQL surface).
- `tests/contract/test_api_contract.py` — the HTTP OGC API contract.
- `tests/test_integration.py` — one end-to-end happy path.

Both generic (derived from a dataset description → run against any dataset) and
fixed golden assertions.

```bash
uv run pytest        # unit tests run without Docker; contract/integration
                     # tests auto-skip if PostGIS isn't up (docker compose up -d db)
```

## Deployment

The engine is shipped as a **engine container image** and deployed to Kubernetes + CloudSQL by a separate
apps repo. See **[DEPLOY.md](DEPLOY.md)** for the operational contract: the `DB_*`
connection vars and `GEOCOMPONENTS_*` settings, the *apply-schema-then-serve*
lifecycle, and the `/healthz` (liveness) + `/datasets` (readiness) probes.

## Future components (designed-for, not built)
- **GML/UML → description factory** (targets the same loader/meta-schema; commons is the integration point).
- **Events** (emit on CRUD/process writes — natural home is the gateway).
- **DB-side validation** (generate CHECK/SRID/code-list constraints — the deferred "validation in the DB").
- **Migrations/evolution** (a `SchemaPlan` diff → migration emitter), versioning/history, more real processes, more DB backends.
