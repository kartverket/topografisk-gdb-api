# topografisk-gdb-api

OGC APIs for topographic geodata, built on
[geocomponents](geocomponents/README.md): datasets are described in YAML, and
both the PostGIS schema and the per-dataset
[OGC API — Features](https://ogcapi.ogc.org/features/) services are generated
from those descriptions.

## Repository layout

- [`geocomponents/`](geocomponents/) — the engine. Start with its
  [README](geocomponents/README.md) for describing datasets and running
  locally; see [DEPLOY.md](geocomponents/DEPLOY.md) for deployment.
- [`nibio/`](nibio/) NIBIO AR5 database dump and schema adjustments. Useful for Postgis Topology integration.
