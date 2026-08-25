# topografisk-gdb-api

OGC APIs for topographic geodata, built on
[geocomponents](geocomponents/README.md): datasets are described in YAML, and
both the PostGIS schema and the per-dataset
[OGC API — Features](https://ogcapi.ogc.org/features/) services are generated
from those descriptions. `gcapi` is the canonical browser-facing facade: it
discovers namespaced collections and synchronous processes from `geocomponents`,
adapts asynchronous import jobs from `gcjobs`, and rewrites links so browser
clients only see one public OGC surface.

System overview (Mermaid): [`ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Repository layout

- [`descriptions/`](descriptions/) — shared dataset YAML declarations used by
  geocomponents and available for reuse by sibling projects.
- [`geocomponents/`](geocomponents/) — the engine. Start with its
  [README](geocomponents/README.md) for describing datasets and running
  locally; see [DEPLOY.md](geocomponents/DEPLOY.md) for deployment.
- [`gcapi/`](gcapi/) — the canonical FastAPI edge service exposing one public
  OGC API over `geocomponents` and `gcjobs`.
- [`gccore/`](gccore/) — a FastAPI service with Alembic-managed tables in the
  shared `gc_core` PostgreSQL schema.
- [`gcjobs/`](gcjobs/) — a FastAPI service with Alembic-managed tables in the
  shared `gc_jobs` PostgreSQL schema.
- [`gcimport/`](gcimport/) — a profile-driven, single-endpoint FastAPI service
  that validates JSON-FG uploads and idempotently imports dataset features.
- [`gcmapview/`](gcmapview/) — local Vite + React map viewer with an `/import`
  page that talks only to `gcapi`, editable Cadastre layers, and read-only
  Bane/Bygning layers on the map.
- [`nibio/`](nibio/) NIBIO AR5 database dump and schema adjustments. Useful for Postgis Topology integration.

## Development

The root `Makefile` provides shortcuts for the local compose stack, the
frontend, and the Python services:

```bash
make lock              # Refresh lockfiles for geocomponents, gcapi, gccore, gcjobs, and gcimport
make install           # Sync dependencies from the existing lockfiles for geocomponents, gcapi, gccore, gcjobs, and gcimport
make docker-up         # Start the local compose stack: PostGIS, geocomponents, gcapi, gcimport, gcmapview, gccore, and gcjobs
make docker-down       # Stop the local compose stack
make docker-delete-db-volume  # Delete the local geocomponents Postgres volume
make docker-trivy-scan # Build and Trivy-scan all Dockerfile-based services via Docker
make frontend-install  # Install frontend dependencies without running scripts
make frontend-build    # Build the frontend
make frontend-run      # Run the frontend development server
make frontend-lint     # Lint the frontend
make frontend-format   # Format the frontend
make gcapi-install     # Install gcapi dependencies
make gcapi-test        # Run gcapi tests
make gcapi-run         # Run gcapi on port 8004
make gccore-install    # Install gccore dependencies
make gccore-test       # Run gccore tests
make gccore-run        # Run gccore on port 8002
make gcjobs-install    # Install gcjobs dependencies
make gcjobs-test       # Run gcjobs tests
make gcjobs-run        # Run gcjobs on port 8003
make gcimport-install  # Install gcimport dependencies
make gcimport-test     # Run gcimport tests
make gcimport-run      # Run gcimport on port 8001
```

To scan container images locally with the same Trivy severity filters as CI:

```bash
# Scan all Dockerfile-based services
make docker-trivy-scan

# Scan only one service image
make docker-trivy-scan SERVICE=gcimport
```

This runs Trivy inside Docker, so no local `trivy` install is required. It
expects a working local Docker daemon and access to the Docker socket.

The repo uses [pre-commit](https://pre-commit.com/) at the root to run various file-hygiene checks at commits. It currently lives in `geocomponents` as a dev tool instead of at root to avoid a root python project and tooling manifest.

The same hooks run in CI (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

The hooks are installed running commands below. [uv](https://docs.astral.sh/uv/) is the only prerequisite:

```bash
# One-time setup: refresh lockfiles, sync environments, install the git hook, and warm hook envs
make lock
make install
uv run --project geocomponents pre-commit install

# Run against staged files (this is what the git hook does)
uv run --project geocomponents pre-commit run

# Run against every file in the repo (this is what CI does)
uv run --project geocomponents pre-commit run --all-files
```

For running the geocomponents test suite (unit tests without Docker,
contract + integration tests against a local PostGIS), see
[`geocomponents/README.md`](geocomponents/README.md#testing).

With `make docker-up`, the local ports are:

- `http://localhost:8000` for geocomponents diagnostics and direct upstream inspection
- `http://localhost:8004` for gcapi and the canonical browser-facing OGC API
- `http://localhost:8001/docs` for gcimport Swagger (internal import worker API)
- `http://localhost:8002/docs` for gccore Swagger
- `http://localhost:8003/docs` for gcjobs Swagger and direct jobs diagnostics
- `http://localhost:8080` for gcmapview

`gcmapview` should only call `gcapi` at `http://localhost:8004`. Direct host
ports for `geocomponents`, `gcjobs`, and `gcimport` remain exposed for
diagnostics and service-local testing, not for browser use.

`gcapi` now exposes a top-level dataset index at `/datasets`, and each public
OGC API is served under `/datasets/{datasetId}/ogc_api/`.

For example:

- `GET /datasets`
- `GET /datasets/cadastre/ogc_api/collections`
- `GET /datasets/cadastre/ogc_api/processes`

Import-related job resources are dataset-scoped as well:

- `GET /datasets/fkb_bane/ogc_api/jobs`
- `GET /datasets/fkb_bane/ogc_api/jobs/{jobID}`
- `GET /datasets/fkb_bane/ogc_api/jobs/{jobID}/results`

To scope jobs to a specific process, use the standard `processID` query
parameter on the dataset-local `/jobs`, for example:

```bash
curl 'http://localhost:8004/datasets/fkb_bane/ogc_api/jobs?type=process&processID=import-fkb-bane'
curl 'http://localhost:8004/datasets/bygning/ogc_api/jobs?type=process&processID=import-bygning&status=successful'
```

For manual import testing against the canonical facade, use the gcapi-owned
dataset-scoped process execution endpoints:

```bash
curl -F 'file=@bane.json;type=application/json' \
  'http://localhost:8004/datasets/fkb_bane/ogc_api/processes/import-fkb-bane/execution'
curl -F 'file=@bygning.geojson;type=application/geo+json' \
  'http://localhost:8004/datasets/bygning/ogc_api/processes/import-bygning/execution'
```

The `201 Created` response includes a `Location` header pointing at the created
job resource under the same dataset-local `/jobs/{jobID}` path.

# Technical details

We are currently using imresamu/postgis:17-3.6-alpine instead of the official postgis/postgis:17-3.6-alpine image for running locally as this resolves missing ARM64 compability in official image.
