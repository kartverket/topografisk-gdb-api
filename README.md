# topografisk-gdb-api

OGC APIs for topographic geodata, built on
[geocomponents](geocomponents/README.md): datasets are described in YAML, and
both the PostGIS schema and the per-dataset
[OGC API — Features](https://ogcapi.ogc.org/features/) services are generated
from those descriptions.

System overview (Mermaid): [`ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Repository layout

- [`geocomponents/`](geocomponents/) — the engine. Start with its
  [README](geocomponents/README.md) for describing datasets and running
  locally; see [DEPLOY.md](geocomponents/DEPLOY.md) for deployment.
- [`gccore/`](gccore/) — a FastAPI service with Alembic-managed tables in the
  shared `gc_core` PostgreSQL schema.
- [`gcjobs/`](gcjobs/) — a FastAPI service with Alembic-managed tables in the
  shared `gc_jobs` PostgreSQL schema.
- [`gcimport/`](gcimport/) — a profile-driven, single-endpoint FastAPI service
  that validates JSON-FG uploads and idempotently imports dataset features.
- [`gcmapview/`](gcmapview/) — local Vite + React map viewer with an `/import`
  page for gcimport, editable Cadastre layers, and read-only Bane/Bygning layers on the map.
- [`nibio/`](nibio/) NIBIO AR5 database dump and schema adjustments. Useful for Postgis Topology integration.

## Development

The root `Makefile` provides shortcuts for starting PostGIS and working with the
frontend:

```bash
make docker-up         # Start the local compose stack: PostGIS, geocomponents, gcimport, gccore, and gcjobs
make frontend-install  # Install frontend dependencies without running scripts
make frontend-build    # Build the frontend
make frontend-run      # Run the frontend development server
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

The repo uses [pre-commit](https://pre-commit.com/) at the root to run various file-hygiene checks at commits.
The same hooks run in CI (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

`pre-commit` itself lives in the `geocomponents` dev dependency group, so
[uv](https://docs.astral.sh/uv/) is the only prerequisite:

```bash
# One-time setup: install the git hook and warm hook envs
uv sync --project geocomponents
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

- `http://localhost:8000` for geocomponents
- `http://localhost:8001/docs` for gcimport Swagger
- `http://localhost:8002/docs` for gccore Swagger
- `http://localhost:8003/docs` for gcjobs Swagger

The default import profile is `bane`; override it with `?profile=bygning` for
Bygning uploads. Example:

```bash
curl -F 'file=@bane.json;type=application/json' http://localhost:8001/imports
```

# Technical details

We are currently using imresamu/postgis:17-3.6-alpine instead of the official postgis/postgis:17-3.6-alpine image for running locally as this resolves missing ARM64 compability in official image.
