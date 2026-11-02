# Deploy geocomponents to SKIP

## Prepare the deployment

In the apps repo, provide a reachable PostGIS database, a secret for its password, and a ConfigMap containing the dataset description files.
Use the published geocomponents image for both the Application and the schema job.

## Configure the Application

Set `DB_HOST`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD` for the database connection.
Set `DB_PORT` if the database does not use port 5432.
For TLS, set `DB_SSLMODE` (prefer `verify-ca`) and, as needed, `DB_SSLROOTCERT`, `DB_SSLCERT`, and `DB_SSLKEY`.
Mount the descriptions as a configMap and set `GEOCOMPONENTS_DESCRIPTIONS` to their path.
Set `GEOCOMPONENTS_BASE_URL` to the external URL for API links.

Add an Application manifest using the published image (the default command is `serve`).
Replace the image, database, secret, ConfigMap, and URL values below:

```yaml
# app.yaml
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
  # Add accessPolicy, replicas, and other deployment settings as needed.
```

## Apply the schema

Add a separate `SKIPJob` for `apply-schema`.
Use the same image, database environment, description mount, and outbound database `accessPolicy` as the Application.
Configure the job to run after the ConfigMap and secrets are synced, and to be recreated on each sync:

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

Check that the job exits successfully and logs `applied schema '<dataset>'` for each dataset.
Then check the Application endpoints at the deployed URL:

```bash
curl -f https://geo.example.org/healthz
curl -f https://geo.example.org/datasets
```

## Update existing datasets

When changing an existing column or table, migrate it manually before syncing the new description.
`apply-schema` creates missing tables and functions but does not migrate existing ones.
Adding a new collection takes effect on the next sync.
