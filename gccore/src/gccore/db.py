from __future__ import annotations

import psycopg
from psycopg import sql

from gccore import config


def health_status() -> dict[str, object]:
    with psycopg.connect(config.psycopg_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            """
            select
                exists (
                    select 1
                    from information_schema.schemata
                    where schema_name = %s
                ),
                exists (
                    select 1
                    from information_schema.tables
                    where table_schema = %s and table_name = 'alembic_version'
                )
            """,
            (config.DB_SCHEMA, config.DB_SCHEMA),
        )
        schema_ready, version_table_ready = cur.fetchone()

        migration_revision = None
        if version_table_ready:
            cur.execute(
                sql.SQL("select version_num from {}.alembic_version limit 1").format(
                    sql.Identifier(config.DB_SCHEMA)
                )
            )
            row = cur.fetchone()
            migration_revision = row[0] if row else None

    return {
        "schema_ready": schema_ready,
        "migration_revision": migration_revision,
    }
