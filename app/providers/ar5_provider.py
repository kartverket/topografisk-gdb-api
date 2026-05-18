import orjson
import psycopg
from psycopg import sql
from pygeoapi.provider.base import BaseProvider, ProviderItemNotFoundError

from app.config import settings


class Ar5FeatureProvider(BaseProvider):
    """
    Generic pygeoapi provider for AR5 topology collections.

    Calls a SQL featurizer function (jsonb_build_object) per row and returns
    the result directly. One provider class handles all AR5 collections;
    the collection-specific config (table, featurizer, geometry column) comes
    from ar5.yaml.
    """

    def __init__(self, provider_def: dict):
        super().__init__(provider_def)
        self.table = provider_def["table"]
        self.featurizer = provider_def["featurizer"]
        self.geometry_column = provider_def["geometry_column"]
        self.native_srid = provider_def["native_srid"]
        self.id_column = provider_def.get("id_field", "identifikasjon_lokal_id")
        schema, table_name = self.table.split(".")
        self._table_id = sql.Identifier(schema, table_name)
        feat_schema, feat_name = self.featurizer.split(".")
        self._featurizer_id = sql.Identifier(feat_schema, feat_name)
        self._id_col_id = sql.Identifier(self.id_column)
        self._geom_col_id = sql.Identifier(self.geometry_column)

    def _connect(self):
        return psycopg.connect(settings.connection_url)

    def _build_where(self, bbox: list) -> tuple[sql.Composable, list]:
        if not bbox:
            return sql.SQL(""), []
        clause = sql.SQL(
            "WHERE ST_Intersects("
            "{geom}::geometry, "
            "ST_Transform(ST_MakeEnvelope(%s, %s, %s, %s, 4326), {srid})"
            ")"
        ).format(
            geom=self._geom_col_id,
            srid=sql.Literal(self.native_srid),
        )
        return clause, list(bbox)

    def query(
        self,
        offset: int = 0,
        limit: int = 10,
        resulttype: str = "results",
        bbox: list = [],
        datetime_=None,
        properties: list = [],
        sortby: list = [],
        select_properties: list = [],
        skip_geometry: bool = False,
        q: str = None,
        filterq=None,
        **kwargs,
    ) -> dict:
        where_clause, params = self._build_where(bbox)

        if resulttype == "hits":
            return {
                "type": "FeatureCollection",
                "features": [],
                "numberReturned": 0,
            }

        feature_query = sql.SQL(
            "SELECT {feat}(t.*)::text"
            " FROM {table} t"
            " {where}"
            " ORDER BY {id_col}"
            " LIMIT %s OFFSET %s"
        ).format(
            feat=self._featurizer_id,
            table=self._table_id,
            where=where_clause,
            id_col=self._id_col_id,
        )

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(feature_query, params + [limit, offset])
                features = [orjson.loads(row[0]) for row in cur]

        return {
            "type": "FeatureCollection",
            "features": features,
            "numberReturned": len(features),
        }

    def get(self, identifier: str, **kwargs) -> dict:
        query = sql.SQL(
            "SELECT {feat}(t.*)::text"
            " FROM {table} t"
            " WHERE {id_col} = %s"
        ).format(
            feat=self._featurizer_id,
            table=self._table_id,
            id_col=self._id_col_id,
        )
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (identifier,))
                row = cur.fetchone()

        if row is None:
            raise ProviderItemNotFoundError()

        return orjson.loads(row[0])
