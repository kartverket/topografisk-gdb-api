# gcmapview

A small Vite + React map viewer for the `geocomponents` OGC API, plus a
JSON-FG upload page that talks to `gcimport`.

Note that this is a small viewer for developer testing, it is not targeted for
wide deployment.

## Routes

- `/` — map with Cadastre (editable) and Bane (read-only) layers
- `/import` — upload a JSON-FG FeatureCollection to `gcimport`

In development, Vite proxies:

- `/geocomponents-api` → `http://localhost:8000`
- `/gcimport-api` → `http://localhost:8001`

## Run

Start geocomponents and gcimport (for example with `make docker-up`), then:

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
