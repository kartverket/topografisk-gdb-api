# Run tests locally

Run these commands from the `geocomponents` directory.
You need `uv` and, for database-backed tests, Docker with Compose.

## Run the full suite

Start the local PostGIS service, then run pytest:

```bash
docker compose up -d db
uv run pytest
```

The host-run tests use PostGIS at `localhost:55432` by default.
The database-backed fixtures create and drop the dataset, `ogc`, and `topogdb` schemas: use a disposable test database, not one containing data you need to keep.
To target a different test database, set `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` before running pytest.

## Run without PostGIS

```bash
uv run pytest
```

When PostGIS cannot be reached, tests that require the database are skipped; database-free tests still run.
Check the pytest summary for skipped tests so a passing run is not mistaken for a full contract run.
