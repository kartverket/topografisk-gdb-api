# gcimport

Profile-driven FastAPI service that validates uploaded JSON-FG
FeatureCollections, transforms their geometries to a dataset CRS, and upserts
features through a geocomponents OGC API.

The initial built-in profile is Bane. Its feature types, required properties,
identity fields, target CRS, and default API URL are isolated in
`src/gcimport/profiles/bane.py`. Add another `ImportProfile` to support another
layer without changing the upload endpoint or upstream client.

## Configuration

- `GCIMPORT_API_URL`: target dataset API URL (the Bane profile defaults to
  `http://localhost:8000/datasets/bane/ogc_api`).
- `GCIMPORT_MAX_UPLOAD_BYTES`: maximum uploaded file size in bytes
  (default: `10485760`).
- `GCIMPORT_TIMEOUT_SECONDS`: upstream request timeout in seconds
  (default: `30`).

## Run locally

```sh
uv sync
uv run uvicorn gcimport.app:app --port 8001
```

The service has one business endpoint:

```text
POST /imports
Content-Type: multipart/form-data
file: a UTF-8 JSON-FG FeatureCollection
```

Example:

```sh
curl -F 'file=@bane.json;type=application/json' http://localhost:8001/imports
```

For the Bane profile, `featureType` is matched case-insensitively to
`jernbaneplattformkant` or `spormidt`. JSON-FG `place` is preferred and uses
`coordRefSys` inherited from the place, feature, or FeatureCollection. If
`place` is absent, GeoJSON `geometry` is interpreted as EPSG:4326.

The complete document is validated and transformed before the first upstream
request. Features are then posted individually as `application/geo+json` to
`{GCIMPORT_API_URL}/collections/{collection}/items:upsert`. Because each write is
an upsert keyed by the feature identity, retrying an individual call is
idempotent.
The response reports the stable UUID returned by Bane for every feature.

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
  -e GCIMPORT_API_URL=http://geocomponents:8000/datasets/bane/ogc_api \
  gcimport
```
