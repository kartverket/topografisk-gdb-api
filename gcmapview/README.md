# gcmapview

The production Node server also exposes `/feature-events`, an SSE bridge over
the per-map-layer Redis Streams emitted by geocomponents. Each browser gets an
independent Redis cursor starting at the current stream tail. The Redis read and
SSE response are released when the browser connection closes.

When a change event arrives, the map transforms its aggregate bbox from the
collection's native CRS to CRS84 and ignores changes outside the current view.
It debounces events by collection and refetches only affected, visible
collections using the current viewport bbox. This handles created, moved, and
deleted features while keeping derived 3D and inspection sources synchronized.

Runtime requires `GCAPI_API_URL` and `REDIS_URL`. Vite development can point the
browser at a running production server with `VITE_FEATURE_EVENTS_URL`; it
defaults to `http://localhost:8080/feature-events`.

A small Vite + React map viewer for the canonical `gcapi` OGC facade, plus a
JSON-FG upload page that starts imports through gcapi-owned OGC process
execution endpoints.

Note that this is a small viewer for developer testing, it is not targeted for
wide deployment.

## Routes

- `/` — map with editable Cadastre layers plus read-only FKB-Bane and Bygning layers
- `/import` — upload a JSON-FG or classic GeoJSON FeatureCollection to `gcapi`; the UI auto-detects FKB-Bane vs Bygning when possible, and still lets the user override the profile

Current read-only import-backed layers on the map:

- FKB-Bane: `jernbaneplattformkant`, `spormidt`
- Bygning: `bygning`, `bygning_omrade`, `bygning_senterlinje`, `bygning_posisjon`

In local development and Docker Compose, the browser talks only to:

- `http://localhost:8004` for `gcapi`

## Run

Start the local backend stack (for example with `make docker-up`), then:

```bash
npm install
npm run dev
```

Optional overrides:

```bash
GCAPI_API_URL=http://localhost:8004 \
npm run dev
```

Those variables are required inputs for the frontend runtime. In local
development, set them to the exposed backend ports. In containerized or deployed
environments, set them to the addresses the browser should call.

## Docker

`make docker-up` also starts a containerized `gcmapview` at
`http://localhost:8080`.

Inside Docker, a small read-only Node server serves the built app, falls back
to `index.html` for client-side routes, and renders `/runtime-config.js`
directly from environment variables without writing into the container
filesystem. API calls still go directly from the browser to the exposed backend
addresses.

To make the browser call public API addresses directly in a deployed
environment, set this runtime variable instead:

```bash
GCAPI_API_URL=https://gcapi.example.no
```

When set, `gcmapview` uses that absolute URL in the browser and bypasses the
Node container for API requests. `gcapi` must allow the frontend origin with
CORS for this mode to work.

For Docker Compose, `gcmapview` uses these direct browser URLs by default:

```bash
GCAPI_API_URL=http://localhost:8004
```

The container does not provide built-in fallback values for these. If they are
missing, startup fails fast.

The image is compatible with a read-only root filesystem because it does not
rewrite web-server config or emit runtime assets during startup.

For Kubernetes or another deployed environment, point these at public API
addresses instead, for example:

```yaml
env:
  - name: GCAPI_API_URL
    value: https://gcapi.example.no
```

`gcapi` must allow the `gcmapview` origin through CORS. The local compose file
sets that up for `http://localhost:5173` and `http://localhost:8080`.

This is separate from the internal `gcapi -> geocomponents`, `gcapi -> gcjobs`,
and `gcjobs -> gcimport -> geocomponents` service configuration. Inside the
backend containers, internal service URLs should still point at cluster or
Compose service names. Only `gcmapview` should use the public browser-facing
URL.
