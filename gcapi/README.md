# gcapi

`gcapi` is the canonical browser-facing OGC API facade for this repository.

It discovers dataset collections and synchronous processes from `geocomponents`,
adapts asynchronous import jobs from `gcjobs`, and rewrites links so browser
clients only see one public API surface.

The public root mirrors the `geocomponents` gateway structure:

- `GET /datasets`
- `GET /datasets/{datasetId}/ogc_api/`
- `GET /datasets/{datasetId}/ogc_api/collections`
- `GET /datasets/{datasetId}/ogc_api/processes`

The public asynchronous import surface is dataset-scoped as well:

- `POST /datasets/{datasetId}/ogc_api/processes/{processID}/execution`
- `GET /datasets/{datasetId}/ogc_api/jobs`
- `GET /datasets/{datasetId}/ogc_api/jobs/{jobID}`
- `GET /datasets/{datasetId}/ogc_api/jobs/{jobID}/results`

Process-specific job views are expressed through the dataset-local job list using
query parameters such as `processID`, `status`, `datetime`, `minDuration`, and
`maxDuration`.

## Local development

Required environment variables:

- `GCAPI_PUBLIC_URL`
- `GCAPI_GEOCOMPONENTS_URL`
- `GCAPI_GCJOBS_URL`

Optional environment variables:

- `GCAPI_REQUEST_TIMEOUT_SECONDS`
- `GCAPI_CONNECT_TIMEOUT_SECONDS`
- `GCAPI_MAX_UPLOAD_BYTES`

Run locally with `uv`:

```bash
uv run --project gcapi gcapi serve
```
