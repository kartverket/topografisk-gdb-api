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

In development, Vite proxies:

- `/geocomponents-api` → `http://localhost:8000`
- `/gcimport-api` → `http://localhost:8001`

## Run

Start the local backend stack (for example with `make docker-up`), then:

```bash
npm install
npm run dev
```

Optional overrides:

```bash
VITE_GEOCOMPONENTS_API_URL=http://localhost:8000 \
VITE_GCIMPORT_API_URL=http://localhost:8001 \
npm run dev
```
