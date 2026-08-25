"""DB-backed non-contract tests for ``ogc.transaction`` error boundaries."""

from __future__ import annotations

from uuid import uuid4

import orjson
import psycopg
import pytest

_FEATURE = {
    "type": "Feature",
    "geometry": {
        "type": "MultiPolygon",
        "coordinates": [[[[10, 55], [10, 56], [11, 56], [11, 55], [10, 55]]]],
    },
    "properties": {"label": "ok"},
}


def _transaction(cur, dataset, document):
    cur.execute(
        "select ogc.transaction(%s,%s)",
        (dataset, orjson.dumps(document).decode()),
    )
    return cur.fetchone()[0]


def test_transaction_class_42_deployment_error_propagates_as_psycopg_error(conn):
    broken_name = "_parcels_create_broken"

    with conn.cursor() as cur:
        cur.execute(
            f"alter function cadastre._parcels_create(jsonb) rename to {broken_name}"
        )
        try:
            with pytest.raises(psycopg.Error) as excinfo:
                _transaction(
                    cur,
                    "cadastre",
                    {
                        "semantic": "atomic",
                        "transaction": [
                            {
                                "action": "insert",
                                "collection": "parcels",
                                "feature": {**_FEATURE, "id": str(uuid4())},
                            }
                        ],
                    },
                )
            assert excinfo.value.sqlstate is not None
            assert excinfo.value.sqlstate.startswith("42")
        finally:
            cur.execute(
                f"alter function cadastre.{broken_name}(jsonb) rename to _parcels_create"
            )


def test_every_ogc_function_has_a_sql_comment(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            select
                p.proname,
                pg_get_function_identity_arguments(p.oid),
                obj_description(p.oid, 'pg_proc')
            from pg_proc p
            join pg_namespace n on n.oid = p.pronamespace
            where n.nspname = 'ogc'
            order by p.proname, pg_get_function_identity_arguments(p.oid)
            """
        )
        missing = [
            f"{name}({args})"
            for name, args, description in cur.fetchall()
            if description is None
        ]

    assert missing == []
