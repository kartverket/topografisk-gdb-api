# PostGIS OGC+ API

REST API for storing and querying geographic features based on OGC standards, with custom extensions covering FKB requirements.

## Features

- **CRUD Operations**: Create, read, update, delete GeoJSON features
- **Spatial Queries**: Bounding box filtering with PostGIS spatial indexes
- **Standards**: GeoJSON-compliant input/output
- **Auto-docs**: Interactive API documentation at `/docs`

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Start the API and database
docker-compose up

# API available at http://localhost:8000
# Interactive docs at http://localhost:8000/docs
```

### Local Development

```bash
# Start PostgreSQL with PostGIS (if not using docker-compose)
docker run --name postgis-dev -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=geodata -p 5432:5432 -d postgis/postgis:18-3.6

# Install dependencies
uv sync

# Run the API
uv run --env-file dev.env uvicorn app.main:app --reload
```

## API Endpoints

- `GET /` — Landing page
- `GET /conformance` — API conformance to OGC standards
- `GET /collections` — List of collections in the API
- `GET /collections/{collection_id}` — Collection metadata
- `GET /collections/{collection_id}/items` — All features in a collection
- `POST /collections/{collection_id}items` — Create a feature
- `GET /collections/{collection_id}/items/{feature_id}` — A specific feature
- `PATCH /collections/{collection_id}/items/{feature_id}` — Partial update of feature
- `DELETE /collections/{collection_id}/items/{feature_id}` — Delete a feature

## Architecture

- **FastAPI**: Async web framework
- **PostGIS**: Spatial database extension for PostgreSQL
- **psycopg**: PostgreSQL adapter with connection pooling
- **Pydantic**: Request/response validation
- **uv**: Fast Python package manager

## Configuration

Set `DATABASE_URL` environment variable (default: `postgresql://postgres:postgres@localhost:5432/geodata`).
