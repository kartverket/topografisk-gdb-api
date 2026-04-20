# PostGIS Feature API

REST API for storing and querying geographic features using PostGIS.

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
docker run --name postgis-dev -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=geodata -p 5432:5432 -d postgis/postgis:16-3.4

# Initialize database
docker cp init.sql postgis-dev:/tmp/init.sql
docker exec postgis-dev psql -U postgres -d geodata -f /tmp/init.sql

# Install dependencies
uv sync

# Run the API
uv run uvicorn app.main:app --reload
```

## API Endpoints

- `POST /api/v1/features` — Create a feature
- `GET /api/v1/features/{id}` — Get a feature by ID
- `GET /api/v1/features` — List features (with optional bbox filter)
- `PUT /api/v1/features/{id}` — Update a feature
- `DELETE /api/v1/features/{id}` — Delete a feature
- `GET /api/v1/features/stats/count` — Get feature count

## Example Usage

### Create a Feature

```bash
curl -X POST http://localhost:8000/api/v1/features \
  -H "Content-Type: application/json" \
  -d '{
    "geometry": {
      "type": "Point",
      "coordinates": [10.0, 59.0]
    },
    "properties": {
      "name": "Oslo",
      "category": "capital"
    }
  }'
```

### Query with Bounding Box

```bash
curl "http://localhost:8000/api/v1/features?minx=9&miny=58&maxx=11&maxy=60"
```

## Architecture

- **FastAPI**: Async web framework
- **PostGIS**: Spatial database extension for PostgreSQL
- **psycopg**: PostgreSQL adapter with connection pooling
- **Pydantic**: Request/response validation
- **uv**: Fast Python package manager

## Configuration

Set `DATABASE_URL` environment variable (default: `postgresql://postgres:postgres@localhost:5432/geodata`).

## License

MIT
