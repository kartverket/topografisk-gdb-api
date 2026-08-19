from __future__ import annotations

from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from gcjobs import config


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


def record_import_event(
    event: dict[str, Any],
    *,
    message_id: str | None = None,
) -> dict[str, Any]:
    import_id = str(event["import_id"])
    event_type = str(event["event"])
    total_features = event.get("total_features")
    errors = event.get("errors")
    reason = event.get("reason")
    last_error = None
    if reason or errors:
        last_error = {
            key: value
            for key, value in {
                "reason": reason,
                "errors": errors,
                "collection": event.get("collection"),
                "feature_id": event.get("feature_id"),
            }.items()
            if value is not None
        }

    updates = _run_updates_for_event(event)

    with (
        psycopg.connect(config.psycopg_dsn()) as conn,
        conn.cursor(row_factory=dict_row) as cur,
    ):
        cur.execute(
            sql.SQL(
                """
                insert into {}.import_run (
                    id,
                    profile,
                    dataset_api_path,
                    filename,
                    status,
                    phase,
                    total_features
                )
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (id) do nothing
                """
            ).format(sql.Identifier(config.DB_SCHEMA)),
            (
                import_id,
                event.get("profile"),
                event.get("dataset_api_path"),
                event.get("filename"),
                updates["status"],
                event.get("phase"),
                total_features,
            ),
        )
        cur.execute(
            sql.SQL(
                """
                insert into {}.import_event (import_id, event_type, message_id, payload)
                values (%s, %s, %s, %s::jsonb)
                on conflict (message_id) do nothing
                returning id
                """
            ).format(sql.Identifier(config.DB_SCHEMA)),
            (import_id, event_type, message_id, psycopg.types.json.Jsonb(event)),
        )
        inserted_event = cur.fetchone()
        if inserted_event is None and message_id is not None:
            cur.execute(
                sql.SQL("select * from {}.import_run where id = %s").format(
                    sql.Identifier(config.DB_SCHEMA)
                ),
                (import_id,),
            )
            row = cur.fetchone()
            conn.commit()
            return row or {"id": import_id}
        cur.execute(
            sql.SQL(
                """
                update {}.import_run
                set
                    profile = coalesce(%s, profile),
                    dataset_api_path = coalesce(%s, dataset_api_path),
                    filename = coalesce(%s, filename),
                    status = %s,
                    phase = coalesce(%s, phase),
                    total_features = coalesce(%s, total_features),
                    processed_features = processed_features + %s,
                    succeeded_features = succeeded_features + %s,
                    failed_features = failed_features + %s,
                    processed_batches = processed_batches + %s,
                    succeeded_batches = succeeded_batches + %s,
                    failed_batches = failed_batches + %s,
                    last_error = coalesce(%s::jsonb, last_error),
                    completed_at = case when %s then current_timestamp else completed_at end,
                    last_event_at = current_timestamp,
                    updated_at = current_timestamp
                where id = %s
                returning *
                """
            ).format(sql.Identifier(config.DB_SCHEMA)),
            (
                event.get("profile"),
                event.get("dataset_api_path"),
                event.get("filename"),
                updates["status"],
                event.get("phase"),
                total_features,
                updates["processed_features"],
                updates["succeeded_features"],
                updates["failed_features"],
                updates["processed_batches"],
                updates["succeeded_batches"],
                updates["failed_batches"],
                psycopg.types.json.Jsonb(last_error)
                if last_error is not None
                else None,
                updates["is_terminal"],
                import_id,
            ),
        )
        row = cur.fetchone()
        conn.commit()
    return row or {"id": import_id}


def list_import_runs(*, active_only: bool, limit: int = 50) -> list[dict[str, Any]]:
    predicate = (
        sql.SQL("where status not in ('completed', 'failed')")
        if active_only
        else sql.SQL("")
    )
    with (
        psycopg.connect(config.psycopg_dsn(), row_factory=dict_row) as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            sql.SQL(
                """
                select *
                from {}.import_run
                {}
                order by last_event_at desc
                limit %s
                """
            ).format(sql.Identifier(config.DB_SCHEMA), predicate),
            (limit,),
        )
        return list(cur.fetchall())


def get_import_run(import_id: str) -> dict[str, Any] | None:
    with (
        psycopg.connect(config.psycopg_dsn(), row_factory=dict_row) as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            sql.SQL("select * from {}.import_run where id = %s").format(
                sql.Identifier(config.DB_SCHEMA)
            ),
            (import_id,),
        )
        return cur.fetchone()


def get_import_events(import_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
    with (
        psycopg.connect(config.psycopg_dsn(), row_factory=dict_row) as conn,
        conn.cursor() as cur,
    ):
        cur.execute(
            sql.SQL(
                """
                select id, import_id, event_type, occurred_at, payload
                from {}.import_event
                where import_id = %s
                order by id asc
                limit %s
                """
            ).format(sql.Identifier(config.DB_SCHEMA)),
            (import_id, limit),
        )
        return list(cur.fetchall())


def _run_updates_for_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event["event"])
    batch_size = int(event.get("batch_size") or 0)
    if event_type == "import.batch.succeeded":
        return _run_update_payload(
            status="running",
            counters={
                "processed_features": batch_size,
                "succeeded_features": batch_size,
                "processed_batches": 1,
                "succeeded_batches": 1,
            },
        )
    if event_type == "import.batch.failed":
        return _run_update_payload(
            status="failed",
            counters={
                "processed_features": batch_size,
                "failed_features": batch_size,
                "processed_batches": 1,
                "failed_batches": 1,
            },
            is_terminal=True,
        )

    status = {
        "import.completed.succeeded": "completed",
        "import.completed.failed": "failed",
    }.get(event_type, "running")
    is_terminal = event_type in {
        "import.completed.succeeded",
        "import.completed.failed",
    }
    return _run_update_payload(
        status=status,
        counters=_terminal_counters(event),
        is_terminal=is_terminal,
    )


def _terminal_counters(event: dict[str, Any]) -> dict[str, int] | None:
    if str(event["event"]) != "import.completed.succeeded":
        return None

    processed_features = event.get("processed_features")
    if not isinstance(processed_features, int):
        imported_features = event.get("imported_features")
        processed_features = (
            imported_features if isinstance(imported_features, int) else None
        )
    if processed_features is None or processed_features < 0:
        return None

    return {
        "processed_features": processed_features,
        "succeeded_features": processed_features,
    }


def _run_update_payload(
    *,
    status: str,
    counters: dict[str, int] | None = None,
    is_terminal: bool = False,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "processed_features": 0,
        "succeeded_features": 0,
        "failed_features": 0,
        "processed_batches": 0,
        "succeeded_batches": 0,
        "failed_batches": 0,
        "is_terminal": is_terminal,
    }
    if counters is not None:
        payload.update(counters)
    return payload
