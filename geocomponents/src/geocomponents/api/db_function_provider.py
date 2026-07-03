"""A pygeoapi feature provider that calls *only* the generic DB dispatch layer.

pygeoapi loads this by dotted path (see ``pygeoapi_provider.py``). Every method
forwards to ``ogc.feature_*(dataset, collection, ...)`` — the provider never
references a table name or a per-collection function name. It passes OGC
identifiers (dataset, collection) it was configured with, and returns the
GeoJSON the database produced. pygeoapi then adds the OGC links/paging envelope.

This is the realisation of the contract: **dataset description + OGC identifiers,
not physical names.**
"""

from __future__ import annotations

import orjson
import psycopg
from pygeoapi.provider.base import (
    BaseProvider,
    ProviderItemNotFoundError,
    ProviderQueryError,
)


def _as_feature_dict(item) -> dict:
    if isinstance(item, (bytes, bytearray, str)):
        return orjson.loads(item)
    return item


class DbFunctionProvider(BaseProvider):
    """Forwarder onto ``ogc.feature_*``; holds no SQL of its own beyond the call."""

    def __init__(self, provider_def):
        super().__init__(provider_def)
        # OGC-level identifiers from the description — the only "names" we hold.
        self.dataset = provider_def["dataset"]
        self.collection = provider_def["collection"]
        self.geom_field = provider_def.get("geom_field", "geometry")
        # numberMatched is optional (a full count); default on, configurable.
        self.with_matched = provider_def.get("with_matched", True)
        # Static field metadata (no DB hit) for queryables / schema.
        self._field_defs = provider_def.get("fields", {})

    # -- connection -------------------------------------------------------
    def _connect(self) -> psycopg.Connection:
        try:
            return psycopg.connect(self.data, autocommit=True)
        except psycopg.Error as err:  # pragma: no cover - infra failure
            raise ProviderQueryError(f"DB connection failed: {err}") from err

    # -- metadata ---------------------------------------------------------
    def get_fields(self) -> dict:
        return self._field_defs

    # -- read -------------------------------------------------------------
    def query(  # noqa: PLR0913 - signature dictated by pygeoapi's BaseProvider.query
        self,
        offset=0,
        limit=10,
        resulttype="results",
        bbox=None,
        datetime_=None,
        properties=None,
        sortby=None,
        select_properties=None,
        skip_geometry=False,
        q=None,
        language=None,
        filterq=None,
        crs_transform_spec=None,
        **kwargs,
    ) -> dict:
        bbox_arg = list(bbox) if bbox else None
        # 'hits' wants only the count: ask for zero features, keep numberMatched.
        eff_limit = 0 if resulttype == "hits" else limit
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select ogc.feature_items(%s, %s, %s, %s, %s, %s)",
                (self.dataset, self.collection, bbox_arg, eff_limit, offset,
                 self.with_matched),
            )
            return cur.fetchone()[0]

    def get(self, identifier, **kwargs) -> dict:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select ogc.feature_item(%s, %s, %s)",
                (self.dataset, self.collection, identifier),
            )
            feature = cur.fetchone()[0]
        if feature is None:
            raise ProviderItemNotFoundError(f"item {identifier} not found")
        return feature

    # -- write (OGC API Features Part 4) ----------------------------------
    def create(self, item) -> str:
        feature = _as_feature_dict(item)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select ogc.feature_create(%s, %s, %s)",
                (self.dataset, self.collection, orjson.dumps(feature).decode()),
            )
            return str(cur.fetchone()[0])

    def update(self, identifier, item) -> bool:
        # OGC PUT == full replace.
        feature = _as_feature_dict(item)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select ogc.feature_replace(%s, %s, %s, %s)",
                (self.dataset, self.collection, identifier, orjson.dumps(feature).decode()),
            )
            ok = cur.fetchone()[0]
        if not ok:
            raise ProviderItemNotFoundError(f"item {identifier} not found")
        return True

    def patch(self, identifier, item) -> bool:
        # OGC PATCH == partial update: only keys present in `item` change.
        feature = _as_feature_dict(item)
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select ogc.feature_update(%s, %s, %s, %s)",
                (self.dataset, self.collection, identifier, orjson.dumps(feature).decode()),
            )
            ok = cur.fetchone()[0]
        if not ok:
            raise ProviderItemNotFoundError(f"item {identifier} not found")
        return True

    def delete(self, identifier) -> bool:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "select ogc.feature_delete(%s, %s, %s)",
                (self.dataset, self.collection, identifier),
            )
            ok = cur.fetchone()[0]
        if not ok:
            raise ProviderItemNotFoundError(f"item {identifier} not found")
        return True

    def __repr__(self):
        return f"<DbFunctionProvider {self.dataset}/{self.collection}>"
