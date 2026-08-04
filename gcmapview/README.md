# gcmapview

A small Vite + React map viewer for the `geocomponents` OGC API.

In development, Vite proxies `/geocomponents-api` to the local API on
`http://localhost:8000`, avoiding browser CORS checks between Vite and
geocomponents. The app renders the `cadastre/parcels` collection from:

```text
/geocomponents-api/datasets/cadastre/ogc_api/collections/parcels/items?f=json&limit=1000
```

The map also loads `cadastre/buildings`. Use **Create random building** to POST a
new `MultiPolygon` building inside the current map view. The generated footprint
is between 20 and 200 square meters. Each building gets a surrounding parcel
with approximately fifteen times the main building's area. Some parcels also
receive a smaller secondary outbuilding.

## Run

Start the API from `geocomponents`, then run the viewer:

```bash
npm install
npm run dev
```

For a deployed app, or if you do want to call another API host directly, set:

```bash
VITE_GEOCOMPONENTS_API_URL=http://localhost:8000 npm run dev
```
