# gcmapview

A small Vite + React map viewer for the `geocomponents` OGC API, plus a
JSON-FG upload page that talks to `gcimport`.

Note that this is a small viewer for developer testing, it is not targeted for
wide deployment.

## Routes

- `/` — map with editable Cadastre layers plus read-only FKB-Bane and Bygning layers
- `/import` — upload a JSON-FG or classic GeoJSON FeatureCollection to `gcimport`; the UI auto-detects FKB-Bane vs Bygning when possible, and still lets the user override the profile

Current read-only import-backed layers on the map:

- FKB-Bane: `jernbaneplattformkant`, `spormidt`
- Bygning: `bygning`, `bygning_omrade`, `bygning_senterlinje`, `bygning_posisjon`

In local development and Docker Compose, the browser talks directly to:

- `http://localhost:8000` for `geocomponents`
- `http://localhost:8001` for `gcimport`

## Run

Start the local backend stack (for example with `make docker-up`), then:

```bash
npm install
npm run dev
```

Optional overrides:

```bash
GEOCOMPONENTS_API_URL=http://localhost:8000 \
GCIMPORT_API_URL=http://localhost:8001 \
npm run dev
```

Those variables are required inputs for the frontend runtime. In local
development, set them to the exposed backend ports. In containerized or deployed
environments, set them to the addresses the browser should call.

## Docker

`make docker-up` also starts a containerized `gcmapview` at
`http://localhost:8080`.

Inside Docker, Nginx serves the built app, falls back to `index.html` for
client-side routes. API calls still go directly from the browser to the exposed
backend addresses.

To make the browser call public API addresses directly in a deployed
environment, set these optional runtime variables instead:

```bash
GEOCOMPONENTS_API_URL=https://geocomponents.example.no
GCIMPORT_API_URL=https://gcimport.example.no
```

When set, `gcmapview` uses those absolute URLs in the browser and bypasses the
Nginx container for API requests. The target APIs must allow the frontend
origin with CORS for this mode to work.

For Docker Compose, `gcmapview` uses these direct browser URLs by default:

```bash
GEOCOMPONENTS_API_URL=http://localhost:8000
GCIMPORT_API_URL=http://localhost:8001
```

The container does not provide built-in fallback values for these. If they are
missing, startup fails fast.

For Kubernetes or another deployed environment, point these at public API
addresses instead, for example:

```yaml
env:
  - name: GEOCOMPONENTS_API_URL
    value: https://geocomponents.example.no
  - name: GCIMPORT_API_URL
    value: https://gcimport.example.no
```

`geocomponents` and `gcimport` must allow the `gcmapview` origin through CORS.
The local compose file sets that up for `http://localhost:5173` and
`http://localhost:8080`.

This is separate from the `gcimport` service's own `GCIMPORT_API_URL`
configuration. Inside the `gcimport` container, `GCIMPORT_API_URL` should still
point at the internal `geocomponents` Service URL in Kubernetes. Only
`gcmapview` should use public browser-facing URLs.
