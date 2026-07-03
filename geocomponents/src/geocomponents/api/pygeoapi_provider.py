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

import pygeoapi.api as core_api
import pygeoapi.api.itemtypes as itemtypes_api
import pygeoapi.api.processes as processes_api
import pygeoapi.l10n as _l10n
from pygeoapi.api import API, APIRequest, apply_gzip
from pygeoapi.openapi import get_oas
from pygeoapi.plugin import load_plugin
from pygeoapi.provider.base import ProviderItemNotFoundError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp

from ..config import database_dsn
from ..descriptions.models import ResolvedCollection, ResolvedDataset
from ..processes.registry import PROCESS_REGISTRY

PROVIDER_PATH = "geocomponents.api.db_function_provider.DbFunctionProvider"
CRS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"


# pygeoapi's HTML rendering memoizes the *translated config* in the module-global
# ``l10n._cfg_cache`` keyed only by locale (see ``l10n.translate_struct``). That
# assumes a single global config per process — but we run one ``API`` per dataset
# in one process, so the first dataset's config would be cached and reused for
# every dataset's HTML chrome (links/title/static). Replace the cache with a
# no-op mapping so each render translates its own per-instance config. JSON never
# uses this path; the cost is only re-translating a small config on HTML renders.
class _NoConfigCache(dict):
    def get(self, key, default=None):  # noqa: D401 - always miss
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
    return "string"


def _provider_fields(coll: ResolvedCollection) -> dict:
    fields = {f.name: {"type": _json_type(f.sql_type)} for f in coll.fields}
    for rel in coll.relationships:
        fields[f"{rel.name}_id"] = {"type": "string"}
    return fields


def _collection_resource(dataset: str, coll: ResolvedCollection, dsn: str) -> dict:
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
            }
        ],
    }


def build_config(dataset: ResolvedDataset, public_url: str, dsn: str) -> dict:
    resources: dict[str, dict] = {
        coll.name: _collection_resource(dataset.name, coll, dsn)
        for coll in dataset.collections
    }
    # OGC API - Processes: only the processes this dataset declares.
    for process_id in dataset.processes:
        resources[process_id] = {
            "type": "process",
            "processor": {"name": PROCESS_REGISTRY[process_id]},
        }

    return {
        "server": {
            "bind": {"host": "0.0.0.0", "port": 8000},
            "url": public_url,
            "mimetype": "application/json",
            "encoding": "utf-8",
            "language": "en-US",
            "languages": ["en-US"],
            "gzip": False,
            "cors": True,
            "pretty_print": True,
            "limits": {"default_items": 10, "max_items": 1000},
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
        {"code": "MethodNotAllowed",
         "description": "Collection is not editable (topology / shared geometry)"},
        status_code=405,
        headers={"Allow": "GET"},
    )


def _options(allow: str) -> Response:
    return Response(status_code=200, headers={"Allow": allow})


def _build_starlette_app(api_: API) -> Starlette:
    def _resource(cid):
        return api_.config["resources"].get(cid)

    def _editable(cid) -> bool:
        res = _resource(cid)
        return bool(res and res["providers"][0].get("editable"))

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
        cid = request.path_params.get("collection_id")
        return await _execute(api_, core_api.describe_collections, request, cid)

    # -- /items : one handler per verb, dispatched by a map (see routes) ----
    async def _list_items(request: Request, cid):
        return await _execute(
            api_, itemtypes_api.get_collection_items, request, cid,
            skip_valid_check=True)

    async def _options_items(_request: Request, cid):
        # POST advertised only when editable.
        write_verbs = ", POST" if _editable(cid) else ""
        return _options("GET, HEAD, OPTIONS" + write_verbs)

    async def _post_items(request: Request, cid):
        # OGC overloads POST: a JSON/GeoJSON body is a Part-4 *create*; any other
        # content-type is a Part-3 *query* (e.g. CQL in the body).
        ct = request.headers.get("content-type", "")
        if not (ct.startswith("application/geo+json")
                or ct.startswith("application/json")):
            return await _list_items(request, cid)
        if not _editable(cid):
            return _not_editable()
        return await _execute(
            api_, itemtypes_api.manage_collection_item, request,
            "create", cid, skip_valid_check=True)

    items_handlers = {
        "OPTIONS": _options_items, "GET": _list_items, "HEAD": _list_items,
        "POST": _post_items,
    }

    async def collection_items(request: Request):
        cid = request.path_params["collection_id"]
        return await items_handlers[request.method](request, cid)

    # -- /items/{item_id} : one handler per verb, dispatched by a map -------
    async def _get_item(request: Request, cid, iid):
        return await _execute(
            api_, itemtypes_api.get_collection_item, request, cid, iid)

    async def _options_item(_request: Request, cid, _iid):
        # Writable verbs (PUT/PATCH/DELETE) advertised only when editable.
        write_verbs = ", PUT, PATCH, DELETE" if _editable(cid) else ""
        return _options("GET, HEAD, OPTIONS" + write_verbs)

    async def _put_item(request: Request, cid, iid):
        if not _editable(cid):
            return _not_editable()
        return await _execute(
            api_, itemtypes_api.manage_collection_item, request,
            "update", cid, iid, skip_valid_check=True)

    async def _delete_item(request: Request, cid, iid):
        if not _editable(cid):
            return _not_editable()
        return await _execute(
            api_, itemtypes_api.manage_collection_item, request,
            "delete", cid, iid, skip_valid_check=True)

    async def _patch_item(request: Request, cid, iid):
        if not _editable(cid):
            return _not_editable()
        # PATCH (partial update) isn't routed by pygeoapi's
        # manage_collection_item, so we call the provider's patch() directly.
        provider = load_plugin("provider", _resource(cid)["providers"][0])
        try:
            provider.patch(iid, await request.body())
        except ProviderItemNotFoundError:
            return JSONResponse(
                {"code": "NotFound", "description": f"item {iid} not found"},
                status_code=404)
        return Response(status_code=204)

    item_handlers = {
        "OPTIONS": _options_item, "GET": _get_item, "HEAD": _get_item,
        "PUT": _put_item, "PATCH": _patch_item, "DELETE": _delete_item,
    }

    async def collection_item(request: Request):
        cid = request.path_params["collection_id"]
        iid = request.path_params["item_id"]
        return await item_handlers[request.method](request, cid, iid)

    async def processes(request: Request):
        pid = request.path_params.get("process_id")
        return await _execute(api_, processes_api.describe_processes, request, pid)

    async def execute_process(request: Request):
        pid = request.path_params["process_id"]
        return await _execute(
            api_, processes_api.execute_process, request, pid,
            skip_valid_check=True)

    routes = [
        Route("/", landing),
        Route("/openapi", openapi),
        Route("/conformance", conformance),
        Route("/collections", collections),
        Route("/collections/{collection_id}", collections),
        Route("/collections/{collection_id}/items", collection_items,
              methods=["GET", "POST", "OPTIONS"]),
        Route("/collections/{collection_id}/items/{item_id}", collection_item,
              methods=["GET", "PUT", "PATCH", "DELETE", "OPTIONS"]),
        Route("/processes", processes),
        Route("/processes/{process_id}", processes),
        Route("/processes/{process_id}/execution", execute_process,
              methods=["POST"]),
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
        openapi = get_oas(config)
        api_ = API(config, openapi)
        return _build_starlette_app(api_)
