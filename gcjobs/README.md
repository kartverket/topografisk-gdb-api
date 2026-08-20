# gcjobs

`gcjobs` is a FastAPI service with its own Alembic-managed schema inside the
shared PostgreSQL database used by `geocomponents`.

- Shared database: same `DB_*` environment variables as `geocomponents`
- Shared Redis broker for the import-event stream: set `REDIS_URL`
- Owned schema: `gc_jobs`
- Migration entrypoint: `gcjobs migrate-db`

## Run locally

```sh
uv sync
export REDIS_URL=redis://localhost:56379/0
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

## Development

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
