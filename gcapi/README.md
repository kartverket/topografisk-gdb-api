# gcapi

`gcapi` is the canonical browser-facing OGC API facade for this repository.

It is a thin reverse proxy in front of `geocomponents`, `gcjobs`, and mock
authorization in `gccore`.

`gcapi` does not model dataset structure, synthesize OpenAPI, or rewrite
upstream JSON/link payloads. It forwards the incoming request method, path,
query string, headers, and body to the configured upstream and returns the
upstream response as-is.

Most requests go to `geocomponents`. Dataset-scoped import process requests
matching `/datasets/{dataset}/ogc_api/processes/import...` and dataset job
requests matching `/datasets/{dataset}/ogc_api/jobs...` are forwarded to
`gcjobs` when `GCAPI_GCJOBS_URL` is configured.

All non-health requests pass through a mock authorization call in `gcapi`.
For now `gcapi` always calls `gccore /authorize` with `{"client_id": null}`
before proxying the request. This simulates a future setup where a fronting
reverse proxy handles authentication and passes authenticated client context to
`gcapi` for authorization. Successful authorization decisions are cached in
process for 10 minutes using a `client_id`-derived cache key.

The only local endpoint is:

- `GET /healthz`

## Local development

Required environment variables:

- `GCAPI_GEOCOMPONENTS_URL`

Optional environment variables:

- `GCAPI_GCJOBS_URL`
- `GCAPI_GCCORE_URL` defaults to `http://localhost:8002`
- `GCAPI_REQUEST_TIMEOUT_SECONDS`
- `GCAPI_CONNECT_TIMEOUT_SECONDS`
- `GCAPI_MAX_UPLOAD_BYTES`

Run locally with `uv`:

```bash
uv run --project gcapi gcapi serve
```
