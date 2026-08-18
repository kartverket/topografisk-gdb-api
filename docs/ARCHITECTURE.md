# System architecture

Current overview of **topografisk-gdb-api** as implemented in this workspace: YAML-described topographic datasets become PostGIS schemas and OGC API - Features services through `geocomponents`. `gcimport` validates and transforms uploaded FeatureCollections, then upserts them through the generated OGC API. `gcmapview` is a local developer frontend for inspection, editing of the Cadastre example dataset, and import testing.

The tracked runtime in this repo is centered on HTTP and PostgreSQL/PostGIS. There is no message queue and no tracked background-job service wired into the running stack.

For package-level detail see [geocomponents/README.md](../geocomponents/README.md), [gcimport/README.md](../gcimport/README.md), [gcmapview/README.md](../gcmapview/README.md), and [geocomponents/DEPLOY.md](../geocomponents/DEPLOY.md).

---

## Context

```mermaid
flowchart TB
  User["Developer / browser"]
  FE["gcmapview<br/>Vite + React + MapLibre"]
  IMP["gcimport<br/>FastAPI importer"]
  API["geocomponents<br/>gateway + per-dataset OGC APIs"]
  DB[("PostgreSQL / PostGIS")]
  OSM["OpenStreetMap tiles<br/>basemap only"]

  User --> FE
  FE -->|multipart upload| IMP
  FE -->|OGC API requests| API
  FE -->|raster tiles| OSM
  IMP -->|items:upsert over HTTP| API
  API -->|ogc.feature_* dispatch| DB
```

## Monorepo packages

| Package | Role now |
|---------|----------|
| [geocomponents/](../geocomponents/) | Description-driven engine: YAML loader, schema generator, OGC API provider, and gateway |
| [gcimport/](../gcimport/) | Profile-driven synchronous importer for JSON-FG and classic GeoJSON uploads |
| [gcmapview/](../gcmapview/) | Local Vite/React developer map viewer and import UI |
| [gccore/](../gccore/) | Placeholder sibling package directory; no tracked runtime code in this workspace yet |
| [gcjobs/](../gcjobs/) | Placeholder sibling package directory; no tracked runtime code in this workspace yet |
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
    MIG["migrate<br/>geocomponents apply-schema"]
    API["api<br/>geocomponents serve :8000"]
    IMP["gcimport<br/>:8001 -> 8000"]

    DB --> MIG --> API
    API --> IMP
  end

  FE -->|/geocomponents-api| API
  FE -->|/gcimport-api| IMP
  IMP -->|HTTP items:upsert| API
  API -->|ogc.feature_*| DB
```

Notes:

- Vite rewrites `/geocomponents-api` to `http://localhost:8000` and `/gcimport-api` to `http://localhost:8001`.
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

`gcimport` is a small FastAPI composition root plus profile definitions and import helpers. In this workspace it exposes a single synchronous upload endpoint, not an async batch/job API.

```mermaid
flowchart LR
  U["Upload client"] --> APP["gcimport.app<br/>POST /imports"]
  APP --> CONV["GeoJSON -> JSON-FG conversion<br/>when filename ends with .geojson"]
  CONV --> PREP["prepare_document()<br/>validate + normalize + CRS transform"]
  PREP --> PROF["ImportProfile routing"]
  PROF --> UP["import_features()<br/>POST collection/items:upsert"]
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
- The response reports the stable UUID returned by the upstream API for each imported feature.

---

## gcmapview component view

`gcmapview` is intentionally a developer-facing client, not a general deployment target. It has two routes: `/` for map inspection/editing and `/import` for uploads to `gcimport`.

```mermaid
flowchart LR
  APP["App routes<br/>/ and /import"]
  IMPUI["ImportView"]
  MAP["MapView"]
  API1["geocomponentsApi.ts"]
  API2["gcimportApi.ts"]
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
  participant I as gcimport
  participant G as geocomponents
  participant DB as PostGIS

  U->>I: POST /imports?profile=fkb_bane|bygning
  alt classic GeoJSON filename
    I->>I: convert_document()
  end
  I->>I: prepare_document()
  loop each feature
    I->>G: POST /collections/{collection}/items:upsert
    G->>DB: ogc.feature_upsert
    DB-->>G: stable UUID
    G-->>I: imported feature response
  end
  I-->>U: FeatureCollection import summary
```

### Map flow

```mermaid
flowchart LR
  MV["gcmapview MapView"]
  CAD["cadastre OGC API"]
  BANE["fkb_bane OGC API"]
  BYG["bygning OGC API"]
  OSM["OSM tiles"]

  MV --> OSM
  MV -->|bbox / collection fetches| CAD
  MV -->|bbox / collection fetches| BANE
  MV -->|bbox / collection fetches| BYG
  MV -->|create/update example features| CAD
```

Frontend rendering specifics that matter architecturally:

- Projected source data is fetched from the API and reprojected client-side for display.
- 3D derived geometry is computed in browser code rather than persisted server-side.
- Terrain-aware and Z-adjusted rendering are visualization concerns in `gcmapview`; source data stays authoritative in the API/database.

---

## Production topology

Production deployment documented in this repo still applies to `geocomponents` only: the engine image is deployed from a separate apps repo, dataset descriptions are mounted at runtime, and schema application is run as a separate one-shot job before the serving application.

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
| Database | PostgreSQL + PostGIS |
| Frontend | Vite, React Router, MapLibre GL, Zustand, Tailwind |
| Geometry / CRS | PostGIS, pyproj, proj4 |
| Data formats | OGC API - Features, GeoJSON, JSON-FG |

---

## Architectural invariants

1. **YAML descriptions drive schema and API surface**. The repo does not hand-maintain dataset-specific SQL tables or HTTP handlers.
2. **`ogc.feature_*` is the backend contract boundary**. Generated functions isolate the API layer from physical dataset tables.
3. **`gcimport` is profile-driven and synchronous in the current codebase**. It validates first, then upserts feature-by-feature through the OGC API.
4. **`gcmapview` owns visualization-only concerns** such as client reprojection, 2D/3D switching, terrain handling, and derived elevated geometry.
5. **Only `geocomponents` is a documented deployed backend from this repo today**. `gcmapview` is local/dev-focused, and `gccore` / `gcjobs` are not part of the tracked runtime in this workspace.
