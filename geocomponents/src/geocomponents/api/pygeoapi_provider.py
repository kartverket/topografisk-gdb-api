"""pygeoapi implementation of ``DatasetApiProvider``.

For one dataset it builds:
  * a pygeoapi config whose resources are the dataset's collections, each wired
    to :class:`DbFunctionProvider` (so data access goes through ``ogc.feature_*``),
  * a per-dataset ``API`` object (constructed directly, *not* from pygeoapi's
    env-global app), and
  * a thin Starlette sub-app whose routes only delegate to pygeoapi's OGC
    functions (``core_api.*`` / ``itemtypes_api.*`` / ``processes_api.*``).

All OGC behaviour (GeoJSON, hypermedia links, paging envelope, conformance,
process execution) is pygeoapi's; we add only the per-dataset routing glue,
because pygeoapi's shipped Starlette app is a single env-driven global with no
``create_app(config)`` factory.

The provider is told the ``public_url`` it will be reachable at (for pygeoapi's
``server.url`` so links are correct) but knows nothing about the gateway's
mount-path convention. This is the *only* pygeoapi-aware code besides the
provider; the gateway never imports pygeoapi.
"""

from __future__ import annotations

import orjson
import pygeoapi.api as core_api
import pygeoapi.api.itemtypes as itemtypes_api
import pygeoapi.api.processes as processes_api
import pygeoapi.l10n as _l10n
from pygeoapi.api import API, APIRequest, apply_gzip
from pygeoapi.openapi import get_oas
from pygeoapi.plugin import load_plugin
from pygeoapi.provider.base import ProviderInvalidDataError, ProviderItemNotFoundError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp

from geocomponents.config import database_dsn
from geocomponents.descriptions.models import (
    ResolvedCollection,
    ResolvedDataset,
    ResolvedField,
)
from geocomponents.processes.registry import PROCESS_REGISTRY

PROVIDER_PATH = "geocomponents.api.db_function_provider.DbFunctionProvider"
CRS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
WGS84_SRID = 4326


def _storage_crs_uri(coll: ResolvedCollection) -> str | None:
    if coll.srid == WGS84_SRID:
        return None
    return f"http://www.opengis.net/def/crs/EPSG/0/{coll.srid}"


# pygeoapi's HTML rendering memoizes the *translated config* in the module-global
# ``l10n._cfg_cache`` keyed only by locale (see ``l10n.translate_struct``). That
# assumes a single global config per process — but we run one ``API`` per dataset
# in one process, so the first dataset's config would be cached and reused for
# every dataset's HTML chrome (links/title/static). Replace the cache with a
# no-op mapping so each render translates its own per-instance config. JSON never
# uses this path; the cost is only re-translating a small config on HTML renders.
class _NoConfigCache(dict):
    def get(self, key, default=None):
        return None

    def __setitem__(self, key, value):  # never retain
        pass


_l10n._cfg_cache = _NoConfigCache()


# --------------------------------------------------------------------------
# Config generation
# --------------------------------------------------------------------------
def _json_type(sql_type: str) -> str:
    s = sql_type.lower()
    if s == "integer":
        return "integer"
    if s in ("double precision", "real", "numeric"):
        return "number"
    if s == "boolean":
        return "boolean"
    if s == "jsonb":
        return "object"
    return "string"


def _field_schema(fld: ResolvedField) -> dict:
    """Return a JSON Schema fragment for one resolved field."""
    if fld.sql_type == "jsonb":
        return {
            "type": "object",
            "properties": {sf.name: _field_schema(sf) for sf in fld.sub_fields},
        }
    schema: dict = {"type": _json_type(fld.sql_type)}
    # Enforced codelist values take priority over documentation-only enum hints.
    values = fld.codelist_values or fld.enum
    if values:
        schema["enum"] = list(values)
    return schema


def _provider_fields(coll: ResolvedCollection) -> dict:
    fields = {f.name: _field_schema(f) for f in coll.fields}
    for rel in coll.relationships:
        fields[f"{rel.name}_id"] = {"type": "string"}
    return fields


def _collection_resource(dataset: str, coll: ResolvedCollection, dsn: str) -> dict:
    storage_crs = _storage_crs_uri(coll)
    return {
        "type": "collection",
        "title": coll.title,
        "description": coll.description or coll.title,
        "keywords": [],
        "extents": {
            "spatial": {"bbox": [-180, -90, 180, 90], "crs": CRS84},
        },
        "providers": [
            {
                "type": "feature",
                "name": PROVIDER_PATH,
                "data": dsn,
                "id_field": coll.id_field,
                "geom_field": coll.geometry_field,
                # Writes only for simple-feature collections (topology = reads only).
                "editable": coll.supports_crud,
                # OGC identifiers carried to the provider (no physical names):
                "dataset": dataset,
                "collection": coll.name,
                "fields": _provider_fields(coll),
                # Geometry type/srid so the provider can describe its own schema.
                "geometry_type": coll.geometry_type,
                "srid": coll.srid,
                "upsert_field": coll.upsert_field,
                **(
                    {
                        "storage_crs": storage_crs,
                        "crs": [CRS84, storage_crs],
                        "always_xy": True,
                    }
                    if storage_crs
                    else {}
                ),
            }
        ],
    }


def _process_resource(dataset: ResolvedDataset, process_id: str, dsn: str) -> dict:
    resource = {
        "type": "process",
        "processor": {
            "name": PROCESS_REGISTRY[process_id],
            "dataset": dataset.name,
            "dataset_title": dataset.title,
        },
    }
    if process_id == "upsert-batch":
        provider_defs = {
            coll.name: _collection_resource(dataset.name, coll, dsn)["providers"][0]
            for coll in dataset.collections
            if coll.supports_upsert
        }
        resource["processor"]["provider_defs"] = provider_defs
    return resource


def build_config(dataset: ResolvedDataset, public_url: str, dsn: str) -> dict:
    resources: dict[str, dict] = {
        coll.name: _collection_resource(dataset.name, coll, dsn)
        for coll in dataset.collections
    }
    # OGC API - Processes: only the processes this dataset declares.
    for process_id in dataset.processes:
        resources[process_id] = _process_resource(dataset, process_id, dsn)

    return {
        "server": {
            # S104: intentional — pygeoapi listens inside the container; the
            # host firewall/reverse proxy controls external exposure.
            "bind": {"host": "0.0.0.0", "port": 8000},  # noqa: S104
            "url": public_url,
            "mimetype": "application/json",
            "encoding": "utf-8",
            "language": "en-US",
            "languages": ["en-US"],
            "gzip": False,
            "cors": True,
            "pretty_print": True,
            "limits": {"default_items": 10, "max_items": 10000},
            "map": {
                "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                "attribution": "OpenStreetMap",
            },
        },
        "logging": {"level": "ERROR"},
        "metadata": {
            "identification": {
                "title": dataset.title,
                "description": dataset.description or dataset.title,
                "keywords": [],
                "keywords_type": "theme",
                "terms_of_service": "https://creativecommons.org/licenses/by/4.0/",
                "url": public_url,
            },
            "license": {
                "name": "CC-BY 4.0",
                "url": "https://creativecommons.org/licenses/by/4.0/",
            },
            "provider": {"name": "geocomponents", "url": public_url},
            "contact": {
                "name": "geocomponents",
                "position": "",
                "address": "",
                "city": "",
                "stateorprovince": "",
                "postalcode": "",
                "country": "",
                "phone": "",
                "fax": "",
                "email": "noreply@example.com",
                "url": public_url,
                "hours": "",
                "instructions": "",
                "role": "pointOfContact",
            },
        },
        "resources": resources,
    }


# --------------------------------------------------------------------------
# Per-dataset Starlette app: routes delegate to pygeoapi's OGC functions.
# --------------------------------------------------------------------------
async def _execute(api_: API, fn, request: Request, *args, skip_valid_check=False):
    api_request = await APIRequest.from_starlette(request, api_.locales)
    if not skip_valid_check and not api_request.is_valid():
        headers, status, content = api_.get_format_exception(api_request)
    else:
        headers, status, content = fn(api_, api_request, *args)
        content = apply_gzip(headers, content)
    return Response(content, status_code=status, headers=headers)


def _not_editable() -> Response:
    """Uniform 405 for writes on non-editable (topology) collections.

    405 is the OGC-sanctioned response when a resource only supports GET
    (Features Part 4 §7 error codes). pygeoapi itself returns 400 for
    non-editable providers, so we intercept writes to give the honest 405. CRUD
    on shared geometry will later arrive via processes + Part 11 (Transactions).
    """
    return JSONResponse(
        {
            "code": "MethodNotAllowed",
            "description": "Collection is not editable (topology / shared geometry)",
        },
        status_code=405,
        # RFC 9110 §15.5.6: Allow must list every method the resource supports.
        headers={"Allow": "GET, HEAD, OPTIONS"},
    )


def _options(allow: str) -> Response:
    return Response(status_code=200, headers={"Allow": allow})


def _filtering_unsupported() -> Response:
    """400 for CQL filtering, which the DB dispatch doesn't implement yet.

    ``ogc.feature_items`` only honours bbox/limit/offset; a ``filter`` would be
    silently ignored, so we refuse it plainly. Real CQL will arrive when the DB
    dispatch grows a filter argument (then ``/queryables`` returns too).
    """
    return JSONResponse(
        {
            "code": "InvalidParameter",
            "description": "CQL filtering (filter/filter-lang) is not supported yet",
        },
        status_code=400,
    )


def _unsupported_media_type() -> Response:
    """415 for POST /items with a content-type other than application/geo+json.

    Part 4 create takes geo+json; Part 3/5 (draft) overloads the same endpoint
    for query-by-POST with a CQL2 ``application/json`` body. Since query-by-
    POST isn't implemented, reject anything else rather than misroute the body
    into create.
    """
    return JSONResponse(
        {
            "code": "UnsupportedMediaType",
            "description": "POST /items requires application/geo+json (create). "
            "Query-by-POST (application/json + CQL2 body) is not "
            "supported yet.",
        },
        status_code=415,
        headers={"Accept-Post": "application/geo+json"},
    )


def _invalid_data(exc: ProviderInvalidDataError) -> Response:
    status = int(getattr(exc, "http_status_code", 400))
    description = getattr(exc, "user_msg", None) or str(exc)
    return JSONResponse(
        {"code": "InvalidData", "description": description},
        status_code=status,
    )


def _tailor_oas(oas: dict, dataset: ResolvedDataset) -> dict:
    """Trim the generated OpenAPI to what this service actually serves.

    Two mismatches to fix:

    * pygeoapi advertises async job management (``/jobs``) whenever a process
      exists, but we execute processes synchronously with no job store, so those
      paths would 404. Drop them.
    * pygeoapi conflates OGC Features **Part 3** (query-by-POST with a CQL2 body,
      an ``application/json`` request body + a ``200`` FeatureCollection reply)
      into the **Part 4** create POST on ``/items``. We only implement create, so
      the docs showed a CQL2 filter as the create example. Keep the create half
      (``application/geo+json`` body + ``201``) and drop the query half.
    """
    paths = oas.get("paths", {})
    for path in ("/jobs", "/jobs/{jobId}", "/jobs/{jobId}/results"):
        paths.pop(path, None)
    for path, item in paths.items():
        if not path.endswith("/items"):
            continue
        post = item.get("post")
        if not post:
            continue
        # The create body is application/geo+json; the CQL2 query body is
        # application/json — remove it so the create example isn't a filter.
        post.get("requestBody", {}).get("content", {}).pop("application/json", None)
        # 200 is the query result; a create yields 201.
        post.get("responses", {}).pop("200", None)
    for coll in dataset.collections:
        if not coll.supports_upsert:
            continue
        feature_path = f"/collections/{coll.name}/items"
        feature_schema = (
            paths.get(feature_path, {})
            .get("post", {})
            .get("requestBody", {})
            .get("content", {})
            .get("application/geo+json", {})
            .get("schema", {"type": "object"})
        )
        paths[f"{feature_path}:upsert"] = {
            "post": {
                "operationId": f"upsert_{coll.name}",
                "summary": f"Upsert {coll.title} by business key",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/geo+json": {"schema": feature_schema},
                    },
                },
                "responses": {
                    "200": {
                        "description": "Feature inserted or replaced",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["id"],
                                    "properties": {
                                        "id": {"type": "string", "format": "uuid"}
                                    },
                                }
                            }
                        },
                    }
                },
            }
        }
    return oas


async def _describe_collections(api_: API, request: Request, cid) -> Response:
    """``describe_collections`` with the dangling ``/queryables`` link removed."""
    api_request = await APIRequest.from_starlette(request, api_.locales)
    if not api_request.is_valid():
        headers, status, content = api_.get_format_exception(api_request)
    else:
        headers, status, content = core_api.describe_collections(api_, api_request, cid)
        if "json" in headers.get("Content-Type", "").lower():
            content = orjson.dumps(_strip_queryables_links(orjson.loads(content)))
            headers.pop("Content-Length", None)
        content = apply_gzip(headers, content)
    return Response(content, status_code=status, headers=headers)


def _collection_schema(api_: API, cid) -> Response:
    """Serve the feature JSON Schema from the provider (backs the schema link)."""
    res = api_.config["resources"].get(cid)
    if res is None:
        return JSONResponse(
            {"code": "NotFound", "description": f"collection {cid} not found"},
            status_code=404,
        )
    provider = load_plugin("provider", res["providers"][0])
    _mimetype, doc = provider.get_schema()
    return JSONResponse(doc, media_type="application/schema+json")


def _resource(api_: API, cid):
    return api_.config["resources"].get(cid)


def _editable(api_: API, cid) -> bool:
    res = _resource(api_, cid)
    return bool(res and res["providers"][0].get("editable"))


def _upsertable(api_: API, cid) -> bool:
    res = _resource(api_, cid)
    return bool(res and res["providers"][0].get("upsert_field"))


def _strip_queryables_links(obj):
    """Remove dangling ``queryables`` hypermedia links (endpoint deferred).

    ``describe_collections`` always links each collection to ``/queryables``,
    which we don't route yet. Walk the response and drop those links so the
    machine contract doesn't promise an endpoint that 404s. The ``schema`` link
    is left intact — it now resolves.
    """
    if isinstance(obj, dict):
        links = obj.get("links")
        if isinstance(links, list):
            obj["links"] = [
                ln
                for ln in links
                if not str(ln.get("rel", "")).rstrip("/").endswith("queryables")
            ]
        for value in obj.values():
            _strip_queryables_links(value)
    elif isinstance(obj, list):
        for value in obj:
            _strip_queryables_links(value)
    return obj


def _build_collection_items_handler(api_: API):
    items_handlers = {
        "OPTIONS": _build_items_options_handler(api_),
        "GET": _build_list_items_handler(api_),
        "HEAD": _build_list_items_handler(api_),
        "POST": _build_post_items_handler(api_),
    }

    async def collection_items(request: Request):
        cid = request.path_params["collection_id"]
        return await items_handlers[request.method](request, cid)

    return collection_items


def _build_list_items_handler(api_: API):
    async def _list_items(request: Request, cid):
        if (
            request.query_params.get("filter") is not None
            or request.query_params.get("filter-lang") is not None
        ):
            return _filtering_unsupported()
        return await _execute(
            api_,
            itemtypes_api.get_collection_items,
            request,
            cid,
            skip_valid_check=True,
        )

    return _list_items


def _build_items_options_handler(api_: API):
    async def _options_items(_request: Request, cid):
        write_verbs = ", POST" if _editable(api_, cid) else ""
        return _options("GET, HEAD, OPTIONS" + write_verbs)

    return _options_items


def _build_post_items_handler(api_: API):
    async def _post_items(request: Request, cid):
        ct = request.headers.get("content-type", "")
        if not ct.lower().startswith("application/geo+json"):
            return _unsupported_media_type()
        if not _editable(api_, cid):
            return _not_editable()
        return await _execute(
            api_,
            itemtypes_api.manage_collection_item,
            request,
            "create",
            cid,
            skip_valid_check=True,
        )

    return _post_items


def _build_upsert_item_handler(api_: API):
    async def upsert_item(request: Request):
        cid = request.path_params["collection_id"]
        if not _upsertable(api_, cid):
            return _not_editable()
        ct = request.headers.get("content-type", "")
        if not ct.lower().startswith("application/geo+json"):
            return _unsupported_media_type()
        provider = load_plugin("provider", _resource(api_, cid)["providers"][0])
        try:
            identifier = provider.upsert(await request.body())
        except ProviderInvalidDataError as exc:
            return _invalid_data(exc)
        return JSONResponse({"id": identifier})

    return upsert_item


def _build_collection_item_handler(api_: API):
    item_handlers = {
        "OPTIONS": _build_item_options_handler(api_),
        "GET": _build_get_item_handler(api_),
        "HEAD": _build_get_item_handler(api_),
        "PUT": _build_put_item_handler(api_),
        "PATCH": _build_patch_item_handler(api_),
        "DELETE": _build_delete_item_handler(api_),
    }

    async def collection_item(request: Request):
        cid = request.path_params["collection_id"]
        iid = request.path_params["item_id"]
        return await item_handlers[request.method](request, cid, iid)

    return collection_item


def _build_get_item_handler(api_: API):
    async def _get_item(request: Request, cid, iid):
        return await _execute(
            api_, itemtypes_api.get_collection_item, request, cid, iid
        )

    return _get_item


def _build_item_options_handler(api_: API):
    async def _options_item(_request: Request, cid, _iid):
        write_verbs = ", PUT, PATCH, DELETE" if _editable(api_, cid) else ""
        return _options("GET, HEAD, OPTIONS" + write_verbs)

    return _options_item


def _build_put_item_handler(api_: API):
    async def _put_item(request: Request, cid, iid):
        if not _editable(api_, cid):
            return _not_editable()
        return await _execute(
            api_,
            itemtypes_api.manage_collection_item,
            request,
            "update",
            cid,
            iid,
            skip_valid_check=True,
        )

    return _put_item


def _build_delete_item_handler(api_: API):
    async def _delete_item(request: Request, cid, iid):
        if not _editable(api_, cid):
            return _not_editable()
        return await _execute(
            api_,
            itemtypes_api.manage_collection_item,
            request,
            "delete",
            cid,
            iid,
            skip_valid_check=True,
        )

    return _delete_item


def _build_patch_item_handler(api_: API):
    async def _patch_item(request: Request, cid, iid):
        if not _editable(api_, cid):
            return _not_editable()
        provider = load_plugin("provider", _resource(api_, cid)["providers"][0])
        try:
            provider.patch(iid, await request.body())
        except ProviderInvalidDataError as exc:
            return _invalid_data(exc)
        except ProviderItemNotFoundError:
            return JSONResponse(
                {"code": "NotFound", "description": f"item {iid} not found"},
                status_code=404,
            )
        return Response(status_code=204)

    return _patch_item


def _build_process_handlers(api_: API):
    async def processes(request: Request):
        pid = request.path_params.get("process_id")
        return await _execute(api_, processes_api.describe_processes, request, pid)

    async def execute_process(request: Request):
        pid = request.path_params["process_id"]
        return await _execute(
            api_, processes_api.execute_process, request, pid, skip_valid_check=True
        )

    return processes, execute_process


def _build_starlette_app(api_: API) -> Starlette:
    async def landing(request: Request):
        return await _execute(api_, core_api.landing_page, request)

    async def openapi(request: Request):
        return await _execute(api_, core_api.openapi_, request)

    async def conformance(request: Request):
        # No dataset-wide suppression: a dataset may declare Part 4 conformance
        # even with topology collections, because those collections are marked
        # non-editable and return 405 on writes (per OGC Features Part 4).
        return await _execute(api_, core_api.conformance, request)

    async def collections(request: Request):
        return await _describe_collections(
            api_, request, request.path_params.get("collection_id")
        )

    async def schema(request: Request):
        return _collection_schema(api_, request.path_params["collection_id"])

    collection_items = _build_collection_items_handler(api_)
    collection_item = _build_collection_item_handler(api_)
    upsert_item = _build_upsert_item_handler(api_)
    processes, execute_process = _build_process_handlers(api_)

    routes = [
        Route("/", landing),
        Route("/openapi", openapi),
        Route("/conformance", conformance),
        Route("/collections", collections),
        Route("/collections/{collection_id}", collections),
        Route("/collections/{collection_id}/schema", schema),
        Route(
            "/collections/{collection_id}/items",
            collection_items,
            methods=["GET", "POST", "OPTIONS"],
        ),
        Route(
            "/collections/{collection_id}/items/{item_id}",
            collection_item,
            methods=["GET", "PUT", "PATCH", "DELETE", "OPTIONS"],
        ),
        Route(
            "/collections/{collection_id}/items:upsert",
            upsert_item,
            methods=["POST"],
        ),
        Route("/processes", processes),
        Route("/processes/{process_id}", processes),
        Route("/processes/{process_id}/execution", execute_process, methods=["POST"]),
    ]
    return Starlette(routes=routes)


# --------------------------------------------------------------------------
# The DatasetApiProvider implementation
# --------------------------------------------------------------------------
class PygeoapiProvider:
    """Builds a mountable pygeoapi OGC API app for one dataset.

    Holds only the database connection; the public URL (and hence the mount
    location) is supplied per call by the gateway.
    """

    def __init__(self, dsn: str | None = None):
        self._dsn = dsn or database_dsn()

    def build_app(self, dataset: ResolvedDataset, public_url: str) -> ASGIApp:
        config = build_config(dataset, public_url.rstrip("/"), self._dsn)
        openapi = _tailor_oas(get_oas(config), dataset)
        api_ = API(config, openapi)
        return _build_starlette_app(api_)
