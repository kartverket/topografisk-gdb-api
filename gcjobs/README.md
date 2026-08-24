# gcjobs

`gcjobs` is a FastAPI service with its own Alembic-managed schema inside the
shared PostgreSQL database used by `geocomponents`.

- Shared database: same `DB_*` environment variables as `geocomponents`
- Shared Redis broker for the import-event stream: set `REDIS_URL`
- Import worker target: set `GCJOBS_IMPORT_API_URL` to the gcimport base URL
- Upload limit: `GCJOBS_MAX_UPLOAD_BYTES` defaults to `104857600` (100 MiB)
- Owned schema: `gc_jobs`
- Migration entrypoint: `gcjobs migrate-db`

## Run locally

```sh
uv sync
export REDIS_URL=redis://localhost:56379/0
export GCJOBS_IMPORT_API_URL=http://localhost:8001
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
- `GET /processes` lists the built-in async import processes
- `GET /processes/{process_id}` describes one built-in async import process
- `POST /processes/import-fkb-bane/execution` starts an async FKB-Bane import
- `POST /processes/import-bygning/execution` starts an async Bygning import
- `GET /jobs` returns root-level job resources for import runs
- `GET /jobs/{job_id}` returns one job document
- `GET /jobs/{job_id}/results` returns the terminal summary for a successful job

## Development

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
