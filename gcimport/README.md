# gcimport

Profile-driven FastAPI service that validates uploaded FeatureCollections,
transforms their geometries to a dataset CRS, and upserts features through a
geocomponents OGC API.

Built-in profiles currently cover FKB-Bane and Bygning. Their feature types,
required properties, identity fields, target CRS, and dataset API paths are
isolated under `src/gcimport/profiles/`. Add another `ImportProfile` to support
another layer without changing the upload endpoint or upstream client.

- FKB-Bane routes to `jernbaneplattformkant` and `spormidt` in `EPSG:5973`.
- Bygning routes linework, area footprints, centerlines, and positions into
  `bygning`, `bygning_omrade`, `bygning_senterlinje`, and `bygning_posisjon`
  in `EPSG:5972`.

## Configuration

- `GEOCOMPONENTS_API_URL`: required geocomponents root URL.
- `REDIS_URL`: required Redis broker URL for the import-event stream.
- `GCIMPORT_MAX_UPLOAD_BYTES`: maximum uploaded file size in bytes
  (default: `104857600`).
- `GCIMPORT_TIMEOUT_SECONDS`: upstream request timeout in seconds
  (default: `30`).

## Run locally

```sh
uv sync
export GEOCOMPONENTS_API_URL=http://localhost:8000
export REDIS_URL=redis://localhost:56379/0
uv run uvicorn gcimport.app:app --port 8001
```

## Uploads

```text
POST /imports
Content-Type: multipart/form-data
file: a UTF-8 FeatureCollection
```

Required query parameter:

- `profile=fkb_bane|bygning`: select the built-in import profile for this upload

gcimport always derives the dataset OGC API path from the selected profile.
It keeps the configured geocomponents root and swaps only the dataset path.

- `.json` / `.jsonfg`: JSON-FG (`featureType`, optional `place`, `coordRefSys`)
- `.geojson`: classic GeoJSON with a `crs` member and `properties.objtype`;
  converted automatically before validation

Examples:

```sh
curl -F 'file=@bane.jsonfg;type=application/json' \
  'http://localhost:8001/imports?profile=fkb_bane'
curl -F 'file=@bane.geojson;type=application/geo+json' \
  'http://localhost:8001/imports?profile=fkb_bane'
```

For the FKB-Bane profile, `featureType` / `objtype` is matched case-insensitively to
`jernbaneplattformkant` or `spormidt`, and source linework is stored as
`MultiLineString` in the target dataset. For the Bygning profile,
`objtype` plus source geometry decide whether a feature lands in `bygning`,
`bygning_omrade`, `bygning_senterlinje`, or `bygning_posisjon`; classic
GeoJSON `BygningBru` features are normalized to the `bygning` collection.
JSON-FG `place` is preferred and uses `coordRefSys` inherited from the place,
feature, or FeatureCollection. If `place` is absent, GeoJSON `geometry` is
interpreted as EPSG:4326.

Examples:

```sh
curl -F 'file=@bane.jsonfg;type=application/json' \
  'http://localhost:8001/imports?profile=fkb_bane'
curl -F 'file=@bygning.geojson;type=application/geo+json' \
  'http://localhost:8001/imports?profile=bygning'
```

The complete document is validated and transformed before the first upstream
request. Features are then posted in collection-grouped batches to
`{GEOCOMPONENTS_API_URL}/datasets/.../ogc_api/processes/upsert-batch/execution`.
gcimport requires that upstream batch process; it does not fall back to single-
feature writes. Because each write is an upsert keyed by the feature identity,
retrying an import call is idempotent.
The response reports the stable UUID returned by the upstream dataset for every
feature.

## Offline GeoJSON → JSON-FG conversion

To convert without uploading:

```sh
uv run geojson-to-jsonfg bane.geojson -o bane.jsonfg
uv run geojson-to-jsonfg --profile bygning bygning.geojson -o bygning.jsonfg
```

Pass `--crs EPSG:5973` if the source file has no `crs` member.

## Development

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Container

```sh
docker build -t gcimport .
docker run --rm -p 8000:8000 \
  -e GEOCOMPONENTS_API_URL=http://geocomponents:8000 \
  gcimport
```
