# gcjobs

`gcjobs` is a FastAPI service with its own Alembic-managed schema inside the
shared PostgreSQL database used by `geocomponents`.

- Shared database: same `DB_*` environment variables as `geocomponents`
- Shared descriptions: reads the repo-root `descriptions/` folder by default, or
  `GEOCOMPONENTS_DESCRIPTIONS` when set
- Shared Redis broker for the import-event stream: set `REDIS_URL`
- Import worker target: set `GCJOBS_IMPORT_API_URL` to the gcimport base URL
- Public API base URL: `GCJOBS_API_BASE_URL` controls emitted dataset/job URLs
  and defaults to `http://localhost:8000`
- Upload limit: `GCJOBS_MAX_UPLOAD_BYTES` defaults to `104857600` (100 MiB)
- Owned schema: `gc_jobs`
- Migration entrypoint: `gcjobs migrate-db`

## Run locally

```sh
uv sync
export REDIS_URL=redis://localhost:56379/0
export GCJOBS_IMPORT_API_URL=http://localhost:8001
export GCJOBS_API_BASE_URL=http://localhost:8004
uv run gcjobs migrate-db
uv run gcjobs serve --port 8003
```

Or start the shared local stack from `geocomponents/`:

```sh
docker compose up --build db redis gcjobs-migrate gcjobs
```

## Endpoints

- `GET /` returns the service and schema identity
- `GET /healthz` checks that the shared database is reachable and reports the
  current Alembic revision if migrations have been applied
- `GET /datasets` lists the dataset-scoped OGC API mounts derived from the
  shared descriptions at startup
- `GET /datasets/{dataset}/ogc_api/processes` lists import processes for that
  dataset; datasets that gcimport can execute expose a single `import` process
- `POST /datasets/fkb_bane/ogc_api/processes/import/execution` starts an async
  FKB-Bane import
- `POST /datasets/bygning/ogc_api/processes/import/execution` starts an async
  Bygning import
- `GET /datasets/{dataset}/ogc_api/jobs` returns the jobs for that dataset only
- `GET /datasets/{dataset}/ogc_api/jobs/{job_id}` returns one dataset-scoped
  job document
- `GET /datasets/{dataset}/ogc_api/jobs/{job_id}/results` returns the terminal
  summary for a successful dataset-scoped job

If `gcjobs` starts without any readable shared dataset descriptions, startup now
fails fast instead of serving only root routes with all dataset mounts missing.

## Development

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
