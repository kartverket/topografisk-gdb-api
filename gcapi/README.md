# gcapi

`gcapi` is the canonical browser-facing OGC API facade for this repository.

It discovers dataset collections and synchronous processes from `geocomponents`,
adapts asynchronous import jobs from `gcjobs`, and rewrites links so browser
clients only see one public API surface.

The public asynchronous processing surface follows OGC API - Processes Part 1:

- `POST /processes/{processID}/execution`
- `GET /jobs`
- `GET /jobs/{jobID}`
- `GET /jobs/{jobID}/results`

Process-specific job views are expressed through the root-level job list using
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
