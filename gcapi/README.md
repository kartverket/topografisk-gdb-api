# gcapi

`gcapi` is the canonical browser-facing OGC API facade for this repository.

It is a thin reverse proxy in front of `geocomponents` and `gcjobs`.

`gcapi` does not model dataset structure, synthesize OpenAPI, or rewrite
upstream JSON/link payloads. It forwards the incoming request method, path,
query string, headers, and body to the configured upstream and returns the
upstream response as-is.

Most requests go to `geocomponents`. Dataset-scoped import process requests
matching `/datasets/{dataset}/ogc_api/processes/import...` and dataset job
requests matching `/datasets/{dataset}/ogc_api/jobs...` are forwarded to
`gcjobs` when `GCAPI_GCJOBS_URL` is configured.

The only local endpoint is:

- `GET /healthz`

## Local development

Required environment variables:

- `GCAPI_GEOCOMPONENTS_URL`
- `GCAPI_GCCORE_URL`

Optional environment variables:

- `GCAPI_GCJOBS_URL`
- `GCAPI_REQUEST_TIMEOUT_SECONDS`
- `GCAPI_CONNECT_TIMEOUT_SECONDS`
- `GCAPI_MAX_UPLOAD_BYTES`
- `GCAPI_SESSION_TTL_SECONDS`
- `GCAPI_SESSION_COOKIE_NAME`
- `GCAPI_SESSION_COOKIE_SECURE`
- `GCAPI_SESSION_COOKIE_SAMESITE`

## Authentication

`gcapi` automatically acquires a server-side in-memory session for proxied
requests by calling `GCAPI_GCCORE_URL/auth` when the request has no valid
session cookie.

Current development behavior:

- sessions are stored in memory only and are lost on restart
- sessions are local to a single process and are not shared across instances
- valid sessions are cached for 10 minutes by default
- missing or expired sessions trigger a new auth request
- `/healthz` and CORS preflight requests remain unauthenticated

Run locally with `uv`:

```bash
uv run --project gcapi gcapi serve
```
