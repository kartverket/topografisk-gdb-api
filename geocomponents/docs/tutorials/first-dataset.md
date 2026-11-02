# Create your first dataset

This walkthrough creates a point collection from a description, starts a local database and API, and writes a feature.
Run the commands from the `geocomponents` directory.
You need Docker with Compose and `curl`.

## Describe the dataset

Create a directory for this example:

```bash
mkdir -p example-descriptions
```

Create `example-descriptions/places.yaml` with the following content:

```yaml
name: places
collections:
  - name: points_of_interest
    geometry:
      type: Point
    fields:
      - name: name
        type: string
        required: true
```

This creates a dataset named "places" with a collection of points named "points_of_interest".
The API created in the next step will expose these endpoints, where `<root>` is `http://localhost:8000/datasets/places/ogc_api`:

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `<root>/collections/points_of_interest/items` | List features. |
| `POST` | `<root>/collections/points_of_interest/items` | Create a feature (as shown below). |
| `GET` | `<root>/collections/points_of_interest/items/{featureId}` | Read one feature by ID. |
| `PUT` | `<root>/collections/points_of_interest/items/{featureId}` | Replace a feature. |
| `PATCH` | `<root>/collections/points_of_interest/items/{featureId}` | Update part of a feature. |
| `DELETE` | `<root>/collections/points_of_interest/items/{featureId}` | Delete a feature. |

## Start the database and API

You need to start the database and api and mount the descriptions.
To do this, run the following command in your terminal:

```bash
DESCRIPTIONS_DIR=./example-descriptions GEOCOMPONENTS_BASE_URL=http://localhost:8000 \
  docker compose up --build db api
```

The public URL setting makes the dataset's links and Swagger UI requests use the API on port 8000.
Wait for `applied schema 'places'` and for the API to start listening on port 8000.
Leave this command running and use another terminal for the requests below.

## Write and read a feature

Check that the dataset is available:

```bash
curl -f http://localhost:8000/datasets
```

Create a point in the new collection:

```bash
curl -i -X POST http://localhost:8000/datasets/places/ogc_api/collections/points_of_interest/items \
  -H 'Content-Type: application/geo+json' \
  -d '{"type":"Feature","geometry":{"type":"Point","coordinates":[10,55]},"properties":{"name":"Example place"}}'
```

Read the collection to see the feature you just created:

```bash
curl -f 'http://localhost:8000/datasets/places/ogc_api/collections/points_of_interest/items?f=json'
```

## Explore the API

Open the [places landing page](http://localhost:8000/datasets/places/ogc_api/?f=html) in your browser to browse the dataset and its collections.
Its [Swagger UI](http://localhost:8000/datasets/places/ogc_api/openapi?f=html) shows the dataset's OGC API operations: expand one, choose **Try it out**, fill in the parameters or GeoJSON body, and select **Execute** to send a request.

These single-feature write endpoints are available for simple-features only.
The [OpenAPI document](http://localhost:8000/datasets/places/ogc_api/openapi?f=json) provides the full set of operations and request formats for this dataset.

Stop the Compose command with Ctrl+C when finished.

## Going further

To explore more options for describing your data such as other geometry-types, nested structures or server-assigned fields, have a look at [field descriptions](../reference/field-descriptions.md) and [geometry descriptions](../reference/geometry-descriptions.md).
