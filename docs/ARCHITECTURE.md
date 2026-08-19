# System architecture

Current overview of **topografisk-gdb-api** as implemented in this workspace: YAML-described topographic datasets become PostGIS schemas and OGC API - Features services through `geocomponents`. `gcimport` validates and transforms uploaded FeatureCollections, upserts them through the generated OGC API, and appends import lifecycle events to a Redis Stream. `gcjobs` accepts import requests, proxies them to `gcimport` in the background, consumes those lifecycle events through a Redis consumer group, persists them, and exposes lightweight import-status/history APIs. `gcmapview` remains a local developer frontend for inspection, editing of the Cadastre example dataset, and import testing.

The tracked runtime in this repo is now centered on HTTP, PostgreSQL/PostGIS, and Redis. For the current POC there is one event flow only: `gcimport` appends import events to a Redis Stream, `gcjobs` consumes and acknowledges them through a consumer group, and `gcjobs` PostgreSQL is the durable source of truth for import tracking.

For package-level detail see [geocomponents/README.md](../geocomponents/README.md), [gcimport/README.md](../gcimport/README.md), [gcmapview/README.md](../gcmapview/README.md), and [geocomponents/DEPLOY.md](../geocomponents/DEPLOY.md).

---

## Context

```mermaid
flowchart TB
  User["Developer / browser"]
  FE["gcmapview<br/>Vite + React + MapLibre"]
  IMP["gcimport<br/>FastAPI importer"]
  JOBS["gcjobs<br/>FastAPI jobs/status API"]
  API["geocomponents<br/>gateway + per-dataset OGC APIs"]
  REDIS[("Redis<br/>event fanout")]
  DB[("PostgreSQL / PostGIS")]
  JOBDB[("gcjobs PostgreSQL schema")]
  BASE["Kartverket WMTS raster basemaps<br/>topo / toporaster / topograatone"]
  TERRAIN["AWS Terrain Tiles<br/>raster-dem for 3D terrain"]

  User --> FE
  FE -->|multipart upload| JOBS
  FE -->|OGC API requests| API
  FE -->|import status/history| JOBS
  FE -->|raster tiles| BASE
  FE -->|terrain DEM| TERRAIN
  JOBS -->|proxy /imports| IMP
  IMP -->|items:upsert over HTTP| API
  IMP -->|append import events| REDIS
  REDIS -->|consumer group + persist| JOBS
  API -->|ogc.feature_* dispatch| DB
  JOBS --> JOBDB
```

## Monorepo packages

| Package | Role now |
|---------|----------|
| [geocomponents/](../geocomponents/) | Description-driven engine: YAML loader, schema generator, OGC API provider, and gateway |
| [gcimport/](../gcimport/) | Profile-driven synchronous importer for JSON-FG and classic GeoJSON uploads plus import-event emission |
| [gcmapview/](../gcmapview/) | Local Vite/React developer map viewer and import UI |
| [gccore/](../gccore/) | Placeholder sibling package directory; no tracked runtime code in this workspace yet |
| [gcjobs/](../gcjobs/) | Lightweight jobs/status service: accepts imports asynchronously, consumes Redis Stream import events, persists run history, and exposes current/history APIs |
| [nibio/](../nibio/) | AR5 / topology reference material, not part of the live runtime |

---

## Local runtime topology

`make docker-up` starts the backend stack from [geocomponents/docker-compose.yml](../geocomponents/docker-compose.yml) and [geocomponents/docker-compose.override.yaml](../geocomponents/docker-compose.override.yaml). `make frontend-run` starts the frontend on the host.

```mermaid
flowchart TB
  subgraph Host
    FE["gcmapview<br/>Vite dev server :5173"]
  end

  subgraph "Docker Compose (geocomponents/)"
    DB[("PostGIS<br/>:55432 -> 5432")]
    REDIS[("Redis<br/>:56379 -> 6379")]
    MIG["migrate<br/>geocomponents apply-schema"]
    API["api<br/>geocomponents serve :8000"]
    IMP["gcimport<br/>:8001 -> 8000"]
    JOBS["gcjobs<br/>:8003 -> 8000"]

    DB --> MIG --> API
    API --> IMP
    DB --> JOBS
    REDIS --> IMP
    REDIS --> JOBS
  end

  FE -->|/geocomponents-api| API
  FE -->|GCJOBS_API_URL| JOBS
  JOBS -->|proxy /imports| IMP
  IMP -->|HTTP items:upsert| API
  IMP -->|append import events| REDIS
  REDIS -->|consumer group + persist| JOBS
  API -->|ogc.feature_*| DB
  JOBS -->|gc_jobs.*| DB
```

Notes:

- Vite rewrites `/geocomponents-api` to `http://localhost:8000` and the import UI should target `gcjobs` at `http://localhost:8003`.
- `gcjobs` currently exposes import start and tracking on port `8003`; `gcmapview` should target that public browser URL for `/import`.
- `migrate` is the local analog of the production `apply-schema` job.
- `gcmapview` is not containerized in the local default flow.

---

## geocomponents component view

YAML descriptions remain the source of truth. The engine still breaks cleanly into four seams: descriptions, schema, API adapter, and gateway.

```mermaid
flowchart LR
  subgraph Descriptions
    YAML["descriptions/*.yaml<br/>cadastre, fkb_bane, bygning, hydro, commons"]
    LOAD["loader + resolved models"]
  end

  subgraph Schema
    PLAN["Schema plan builder"]
    DDL["PostGIS DDL<br/>tables + ogc.feature_* functions"]
  end

  subgraph API
    DAP["DatasetApiProvider"]
    PYG["PygeoapiProvider"]
    DBF["DbFunctionProvider"]
  end

  subgraph Gateway
    GW["FastAPI gateway<br/>/datasets<br/>/datasets/{name}/ogc_api<br/>/healthz"]
  end

  YAML --> LOAD --> PLAN --> DDL
  LOAD --> DAP --> PYG --> DBF
  GW --> DAP
  DDL --> PG[("PostGIS")]
  DBF --> PG
```

The important runtime contract is unchanged: the HTTP layer does not talk to physical dataset tables directly. It delegates reads and writes through the generated `ogc.feature_*` dispatch functions.

| HTTP surface | SQL dispatch |
|--------------|--------------|
| `GET .../items` | `ogc.feature_items` |
| `GET .../items/{id}` | `ogc.feature_item` |
| `POST .../items` | `ogc.feature_create` |
| `PUT` / `PATCH` / `DELETE` | `ogc.feature_replace` / `ogc.feature_update` / `ogc.feature_delete` |
| `POST .../items:upsert` | `ogc.feature_upsert` |

Current dataset descriptions in the repo:

- `cadastre`: editable example parcels/buildings plus topology examples
- `fkb_bane`: projected rail/platform collections in `EPSG:5973`
- `bygning`: projected linework, areas, centerlines, and positions in `EPSG:5972`
- `hydro`: additional example dataset

---

## gcimport component view

`gcimport` is a small FastAPI composition root plus profile definitions and import helpers. In this workspace it still exposes a synchronous upload endpoint, and it appends import lifecycle events to a Redis Stream while `gcjobs` owns public import start and tracking.

```mermaid
flowchart LR
  U["Upload client"] --> APP["gcimport.app<br/>POST /imports"]
  APP --> CONV["GeoJSON -> JSON-FG conversion<br/>when filename ends with .geojson"]
  CONV --> PREP["prepare_document()<br/>validate + normalize + CRS transform"]
  PREP --> PROF["ImportProfile routing"]
  PROF --> UP["import_features()<br/>POST collection/items:upsert"]
  APP --> EVT["append import events<br/>started / parsed / batch / completed"]
  EVT --> REDIS["Redis Stream"]
  UP --> API["geocomponents OGC API"]
```

Current built-in profiles:

- `fkb_bane`: routes source features into `jernbaneplattformkant` and `spormidt`, storing projected `MultiLineString` geometry in `EPSG:5973`
- `bygning`: routes by source `objtype` and geometry into `bygning`, `bygning_omrade`, `bygning_senterlinje`, and `bygning_posisjon` in `EPSG:5972`

Request shape now:

```http
POST /imports?profile=fkb_bane|bygning
Content-Type: multipart/form-data
```

The `profile` query parameter is required on every upload request

Behavior now:

- `.geojson` uploads are converted to JSON-FG before validation.
- JSON is validated before the first upstream request.
- Features are grouped by collection and sent in configurable chunks to `.../processes/upsert-batch/execution`; if that process is unavailable, gcimport falls back to per-feature `.../collections/{collection}/items:upsert`.
- Import lifecycle events are appended at parse start, parse completion, per-batch success/failure, and final success/failure.
- Redis Streams are the single event transport from `gcimport` back to `gcjobs`.
- The response reports the stable UUID returned by the upstream API for each imported feature.

---

## gcjobs component view

`gcjobs` is intentionally small in the current POC. It owns public import start and import tracking state. Its durable model is PostgreSQL in the `gc_jobs` schema, and it updates that model by consuming Redis Stream events through a consumer group while the frontend polls status over HTTP.

```mermaid
flowchart LR
  START["POST /imports"] --> ACCEPT["return 202 + import_id"]
  ACCEPT --> PROXY["background proxy to gcimport"]
  EV["Redis Stream event"] --> WRITE["record_import_event()"]
  WRITE --> RUN["gc_jobs.import_run"]
  WRITE --> LOG["gc_jobs.import_event"]
  READ1["GET /imports/current"] --> RUN
  READ2["GET /imports/history"] --> RUN
  READ3["GET /imports/{id}"] --> RUN
  READ4["GET /imports/{id}/events"] --> LOG
  PROXY --> GCIMPORT["gcimport /imports"]
  REDIS["Redis consumer group"] --> WRITE
```

Current responsibilities:

- persist one summary row per import run in `gc_jobs.import_run`
- append raw lifecycle events in `gc_jobs.import_event`
- accept import requests immediately and return `import_id` before import execution completes
- expose lightweight read models for active imports, history, one run, and per-run event history
- consume and acknowledge Redis Stream import events; Redis is transport, `gcjobs` PostgreSQL is the durable source of truth

---

## gcmapview component view

`gcmapview` is intentionally a developer-facing client, not a general deployment target. It has two routes: `/` for map inspection/editing and `/import` for uploads that now start through `gcjobs`.

```mermaid
flowchart LR
  APP["App routes<br/>/ and /import"]
  IMPUI["ImportView"]
  MAP["MapView"]
  API1["geocomponentsApi.ts"]
  API2["importApi.ts"]
  STORE1["layerVisibilityStore"]
  STORE2["mapViewStore<br/>favorites + mode"]
  DATA["mapViewData.ts"]
  GEOM["mapViewGeometry.ts"]
  RAND["mapViewRandomFeatures.ts"]
  SEL["useSelectedFeature.ts"]
  DIM["mapDimension.ts<br/>2D/3D + terrain"]
  WORKER["elevatedSourcesWorker.ts"]
  PICK["featureInspect.ts"]

  APP --> IMPUI --> API2
  APP --> MAP
  MAP --> API1
  MAP --> STORE1
  MAP --> STORE2
  MAP --> DATA
  MAP --> GEOM
  MAP --> RAND
  MAP --> SEL
  MAP --> DIM
  MAP --> PICK
  DIM --> WORKER
```

Current map behavior:

- Cadastre layers are editable in the frontend against the generated OGC API.
- FKB-Bane and Bygning layers are read-only in the frontend.
- Bygning currently includes four map collections: `bygning`, `bygning_omrade`, `bygning_senterlinje`, `bygning_posisjon`.
- `featureInspect.ts` resolves clicks back to registered source features for stable inspection.
- `useSelectedFeature.ts` refetches selected features in their storage CRS for accurate coordinate inspection.
- `mapDimension.ts` owns 2D/3D switching, terrain integration, and heavy elevated-source recalculation.
- `workers/elevatedSourcesWorker.ts` offloads elevated source derivation from the main UI thread.
- `mapViewStore.ts` persists named favorite views, active mode, and visibility-related state locally.

---

## Data flows

### Import flow

```mermaid
sequenceDiagram
  participant U as Uploader
  participant J as gcjobs
  participant I as gcimport
  participant G as geocomponents
  participant DB as PostGIS
  participant JDB as gc_jobs schema

  U->>J: POST /imports?profile=fkb_bane|bygning
  J->>JDB: record import.accepted
  J-->>U: 202 Accepted + import_id
  J->>I: background proxy multipart request + X-Import-Id
  I->>R: publish import.started
  R->>J: import.started
  J->>JDB: upsert import_run + append import_event
  alt classic GeoJSON filename
    I->>I: convert_document()
  end
  I->>I: prepare_document()
  I->>R: publish import.parsed
  R->>J: import.parsed
  J->>JDB: update run + append event
  loop each collection batch or single-feature fallback
    I->>G: POST /collections/{collection}/items:upsert
    G->>DB: ogc.feature_upsert
    DB-->>G: stable UUID
    G-->>I: imported feature response
  end
  I->>R: publish batch/completed events
  R->>J: batch/completed events
  J->>JDB: update run + append event
  FE->>J: GET /imports/{id}
  J-->>FE: phase, counts, batches, status
```

### Message flow

This is the specific import-message path as it exists in the current POC: `gcjobs` owns public import start and status, `gcjobs` returns immediately with `import_id`, Redis is the single event transport from `gcimport`, and the frontend polls `gcjobs` for progress.

```mermaid
sequenceDiagram
  participant FE as Frontend / uploader
  participant J as gcjobs
  participant I as gcimport
  participant R as Redis
  participant JDB as gc_jobs PostgreSQL

  FE->>J: POST /imports
  J->>JDB: store import.accepted
  J-->>FE: 202 Accepted + import_id
  J->>I: background proxy request + X-Import-Id
  I-->>R: publish started
  R-->>J: consume started
  J->>JDB: store summary + raw event

  I-->>R: publish parsed
  R-->>J: consume parsed
  J->>JDB: update run + total feature count

  loop each batch
    I-->>R: publish batch.succeeded|batch.failed
    R-->>J: consume batch.succeeded|batch.failed
    J->>JDB: update counters + append raw event
  end

  I-->>R: publish completed.succeeded|completed.failed
  R-->>J: consume completed.succeeded|completed.failed
  J->>JDB: mark terminal state
  FE->>J: GET /imports/current or /imports/{id}
  J-->>FE: current status / history / raw event list
```

### Map flow

```mermaid
flowchart LR
  MV["gcmapview MapView"]
  CAD["cadastre OGC API"]
  BANE["fkb_bane OGC API"]
  BYG["bygning OGC API"]
  TOPO["Kartverket topo WMTS"]
  RASTER["Kartverket toporaster WMTS"]
  GRAY["Kartverket topograatone WMTS"]
  TERRAIN["AWS Terrain Tiles DEM"]

  MV --> TOPO
  MV --> RASTER
  MV --> GRAY
  MV --> TERRAIN
  MV -->|bbox / collection fetches| CAD
  MV -->|bbox / collection fetches| BANE
  MV -->|bbox / collection fetches| BYG
  MV -->|create/update example features| CAD
```

Frontend rendering specifics that matter architecturally:

- Projected source data is fetched from the API and reprojected client-side for display.
- 3D derived geometry is computed in browser code rather than persisted server-side.
- The map background is not OpenStreetMap; users can switch between Kartverket `topo`, `toporaster`, and `topograatone`, or disable the background entirely.
- Terrain-aware and Z-adjusted rendering are visualization concerns in `gcmapview`; source data stays authoritative in the API/database.
- Import progress is not pushed to the browser from Redis; the browser polls `gcjobs` for parsing state, batch progress, and terminal statistics.

---

## Production topology

Production deployment documented in this repo still applies primarily to `geocomponents`: the engine image is deployed from a separate apps repo, dataset descriptions are mounted at runtime, and schema application is run as a separate one-shot job before the serving application. The newer `gcjobs` and Redis-backed import-tracking path is implemented in this workspace, but its deployment shape is still evolving and is not yet documented here as a production-standard topology.

```mermaid
flowchart LR
  Argo["Argo CD / apps repo"] --> Job["apply-schema job"]
  Argo --> App["geocomponents serve :8000"]
  CM["mounted descriptions"] --> Job
  CM --> App
  Secret["DB env / secrets"] --> Job
  Secret --> App
  Job --> SQL[("PostGIS / Cloud SQL")]
  App --> SQL
```

Operational points:

- liveness probe: `/healthz`
- readiness probe: `/datasets`
- `apply-schema` is create-if-missing and idempotent for repeated runs
- descriptions are supplied at runtime, not baked into the image
- `gcmapview` remains a local/dev tool by default

---

## Technology snapshot

| Layer | Stack now |
|-------|-----------|
| Languages | Python 3.12, TypeScript, React 19 |
| Backend frameworks | FastAPI, Starlette, Uvicorn, pygeoapi |
| Database | PostgreSQL + PostGIS, Redis |
| Frontend | Vite, React Router, MapLibre GL, Zustand, Tailwind |
| Geometry / CRS | PostGIS, pyproj, proj4 |
| Data formats | OGC API - Features, GeoJSON, JSON-FG |

---

## Architectural invariants

1. **YAML descriptions drive schema and API surface**. The repo does not hand-maintain dataset-specific SQL tables or HTTP handlers.
2. **`ogc.feature_*` is the backend contract boundary**. Generated functions isolate the API layer from physical dataset tables.
3. **`gcimport` is profile-driven and synchronous in the current codebase**. It validates first, then imports in collection batches or feature fallback through the OGC API, while emitting lifecycle events to Redis.
4. **`gcmapview` owns visualization-only concerns** such as client reprojection, 2D/3D switching, terrain handling, and derived elevated geometry.
5. **`gcjobs` owns durable import-tracking state in the current POC**. It accepts import requests immediately, persists event-derived state in PostgreSQL, and is the only backend the frontend needs for import start and status.
6. **Only `geocomponents` has a stable production deployment description in this repo today**. `gcmapview` is local/dev-focused, and the newer `gcjobs`/Redis topology is tracked in code but not yet fully described as production infrastructure.
