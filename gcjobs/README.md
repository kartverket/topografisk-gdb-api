# gcjobs

`gcjobs` is a FastAPI service with its own Alembic-managed schema inside the
shared PostgreSQL database used by `geocomponents`.

- Shared database: same `DB_*` environment variables as `geocomponents`
- Owned schema: `gc_jobs`
- Migration entrypoint: `gcjobs migrate-db`

## Run locally

```sh
uv sync
uv run gcjobs migrate-db
uv run gcjobs serve --port 8003
```

Or start the shared local stack from `geocomponents/`:

```sh
docker compose up --build db gcjobs-migrate gcjobs
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