# Deploying the `geocomponents` image

`geocomponents` turns a folder of dataset descriptions into a PostGIS database and
an OGC API. It ships as a container image whose entrypoint is the `geocomponents`
CLI; CI publishes it (e.g. to GHCR) and the manifest lives in the apps repo.

## What the apps repo provides

1. **A database** — set the `DB_*` environment variables.
2. **The dataset descriptions** — mount them as a folder (`filesFrom`) and set
   `GEOCOMPONENTS_DESCRIPTIONS` to that path.

## Commands

- `serve` — runs the API. This is the image default; the main container sets no command.
- `apply-schema` — builds the database schema. Run it as a separate one-shot job
  (a `SKIPJob`), **not** as an init container on the Application — see
  [Applying the schema](#applying-the-schema).

## Environment variables

| Variable | Purpose |
|---|---|
| `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | database connection (required); `DB_PASSWORD` from a secret |
| `DB_PORT` | optional, defaults to 5432 |
| `DB_SSLMODE`, `DB_SSLROOTCERT`, `DB_SSLCERT`, `DB_SSLKEY` | optional TLS (recommend `DB_SSLMODE=verify-ca`) |
| `GEOCOMPONENTS_DESCRIPTIONS` | path to the mounted descriptions folder |
| `GEOCOMPONENTS_BASE_URL` | external URL, used in the OGC API's links |

If the `DB_*` variables are missing, the app exits with an error.

## Manifest

```yaml
apiVersion: skiperator.kartverket.no/v1alpha1
kind: Application
metadata:
  name: geocomponents
spec:
  image: ghcr.io/<org>/geocomponents:<tag>
  port: 8000
  env:
    - { name: DB_HOST, value: "10.0.0.5" }
    - { name: DB_NAME, value: "geocomponents" }
    - { name: DB_USER, value: "geocomponents" }
    - name: DB_PASSWORD
      valueFrom: { secretKeyRef: { name: geocomponents-db, key: password } }
    - { name: GEOCOMPONENTS_DESCRIPTIONS, value: "/etc/geocomponents/descriptions" }
    - { name: GEOCOMPONENTS_BASE_URL, value: "https://geo.example.org" }
  filesFrom:
    - configMap: geocomponents-descriptions
      mountPath: /etc/geocomponents/descriptions
  liveness:  { path: /healthz,  port: 8000 }
  readiness: { path: /datasets, port: 8000 }
```

## Applying the schema

`apply-schema` is a task: it connects, issues the DDL, prints what
it applied, and exits 0. Run it as a `SKIPJob`.

```yaml
apiVersion: skiperator.kartverket.no/v1beta1
kind: SKIPJob
metadata:
  name: geocomponents-apply-schema
  annotations:
    argocd.argoproj.io/hook: PostSync  # Job runs after configMap and secrets exist
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation  #  deletes previous run so job runs on every sync
spec:
  image: ghcr.io/<org>/geocomponents:<tag>
  command: ["geocomponents", "apply-schema"]
  # env, filesFrom and accessPolicy as in app.yaml
```

Three details on applying schema:

- `argocd.argoproj.io/hook: PostSync`: This ensures the job runs after secrets, configmaps etc are applied, ensuring that the job has the necessary resources.
- `hook-delete-policy: BeforeHookCreation`: We need the job to run on changes in descriptions. As the job's spec does not change we need something to trigger the job on every sync. This ensures the old job is deleted when syncing thus running the job again. Safe as `apply-schema` is idempotent.
- Give the job its own `accessPolicy`. It needs the same outbound rule to the
  database as the Application.

## Extra development note

`apply-schema` only creates missing tables/functions; it does not yet migrate a
change to an existing column or table. Adding a new collection to a description
works on the next sync; changing the type of an existing column does not.
See [Not built yet](README.md#not-built-yet-designed-for) in the README.
