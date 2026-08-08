# gcimport

Profile-driven FastAPI service that validates uploaded FeatureCollections,
transforms their geometries to a dataset CRS, and upserts features through a
geocomponents OGC API.

Built-in profiles currently cover Bane and Bygning. Their feature types,
required properties, identity fields, target CRS, and default API URLs are
isolated under `src/gcimport/profiles/`. Add another `ImportProfile` to support
another layer without changing the upload endpoint or upstream client.

## Configuration

- `GCIMPORT_API_URL`: target dataset API URL (the Bane profile defaults to
  `http://localhost:8000/datasets/bane/ogc_api`).
- `GCIMPORT_API_URL_BYGNING`: optional explicit Bygning dataset API URL override
  for `profile=bygning` uploads.
- `GCIMPORT_PROFILE`: built-in profile name (`bane` or `bygning`; default:
  `bane`).
- `GCIMPORT_MAX_UPLOAD_BYTES`: maximum uploaded file size in bytes
  (default: `10485760`).
- `GCIMPORT_TIMEOUT_SECONDS`: upstream request timeout in seconds
  (default: `30`).

## Run locally

```sh
uv sync
uv run uvicorn gcimport.app:app --port 8001
```

## Uploads

```text
POST /imports
Content-Type: multipart/form-data
file: a UTF-8 FeatureCollection
```

Optional query parameter:

- `profile=bane|bygning`: override the app default profile for this upload

When a request profile differs from the app default profile, gcimport retargets
the configured upstream host to that profile's default dataset path. You can
override that explicitly with `GCIMPORT_API_URL_<PROFILE>` variables, for
example `GCIMPORT_API_URL_BYGNING`.

- `.json` / `.jsonfg`: JSON-FG (`featureType`, optional `place`, `coordRefSys`)
- `.geojson`: classic GeoJSON with a `crs` member and `properties.objtype`;
  converted automatically before validation

Examples:

```sh
curl -F 'file=@bane.jsonfg;type=application/json' http://localhost:8001/imports
curl -F 'file=@bane.geojson;type=application/geo+json' http://localhost:8001/imports
```

For the Bane profile, `featureType` / `objtype` is matched case-insensitively to
`jernbaneplattformkant` or `spormidt`. For the Bygning profile,
`BygningBru` classic GeoJSON features are normalized to the `bygning`
collection and single- or multi-part `MultiLineString` geometry is preserved
as linework instead of being split or coerced into polygons.
JSON-FG `place` is preferred and uses `coordRefSys` inherited from the place,
feature, or FeatureCollection. If `place` is absent, GeoJSON `geometry` is
interpreted as EPSG:4326.

Examples:

```sh
curl -F 'file=@bane.jsonfg;type=application/json' \
  'http://localhost:8001/imports?profile=bane'
curl -F 'file=@bygning.geojson;type=application/geo+json' \
  'http://localhost:8001/imports?profile=bygning'
```

The complete document is validated and transformed before the first upstream
request. Features are then posted individually as `application/geo+json` to
`{GCIMPORT_API_URL}/collections/{collection}/items:upsert`. Because each write is
an upsert keyed by the feature identity, retrying an individual call is
idempotent.
The response reports the stable UUID returned by Bane for every feature.

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
  -e GCIMPORT_API_URL=http://geocomponents:8000/datasets/bane/ogc_api \
  gcimport
```
