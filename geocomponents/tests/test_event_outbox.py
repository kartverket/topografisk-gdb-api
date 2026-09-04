from __future__ import annotations

from uuid import UUID

import psycopg

from geocomponents.schema import postgis
from geocomponents.schema.plan import (
    CollectionPlan,
    ColumnPlan,
    GeometryColumnPlan,
    SchemaPlan,
    TablePlan,
)


def _event_plan() -> SchemaPlan:
    table = TablePlan(
        schema="event_contract",
        name="roads",
        columns=(ColumnPlan("localid", "uuid", nullable=False, primary_key=True),),
        geometry=GeometryColumnPlan("shape", "Point", 4326),
    )
    collection = CollectionPlan(
        collection_name="roads",
        feature_model="simple",
        table=table,
        functions={},
    )
    return SchemaPlan(schema_name="event_contract", collections=(collection,))


def _events(connection: psycopg.Connection) -> list[tuple]:
    return connection.execute(
        """
        select localids, operations, srid,
               case when affected_area is null then null else array[
                   ST_XMin(Box2D(affected_area)), ST_YMin(Box2D(affected_area)),
                   ST_XMax(Box2D(affected_area)), ST_YMax(Box2D(affected_area))
               ] end
        from geocomponents_event.change_outbox
        where dataset = 'event_contract' and collection = 'roads'
        order by created_at, id
        """
    ).fetchall()


def test_outbox_groups_transaction_and_aggregates_old_and_new_bounds(db):
    first = UUID("00000000-0000-0000-0000-000000000101")
    second = UUID("00000000-0000-0000-0000-000000000102")
    connection = psycopg.connect(db, autocommit=False)
    try:
        with connection.transaction():
            connection.execute("drop schema if exists event_contract cascade")
            connection.execute(
                "delete from geocomponents_event.change_outbox "
                "where dataset = 'event_contract'"
            )
        postgis.apply_tables(connection, _event_plan())

        with connection.transaction():
            connection.execute(
                "insert into event_contract.roads (localid, shape) values "
                "(%s, ST_SetSRID(ST_Point(0, 0), 4326)), "
                "(%s, ST_SetSRID(ST_Point(4, 5), 4326))",
                (first, second),
            )

        assert _events(connection) == [
            ([first, second], ["create"], 4326, [0.0, 0.0, 4.0, 5.0])
        ]

        with connection.transaction():
            connection.execute(
                "update event_contract.roads "
                "set shape = ST_SetSRID(ST_Point(10, 12), 4326) "
                "where localid = %s",
                (first,),
            )

        assert _events(connection)[1] == (
            [first],
            ["update"],
            4326,
            [0.0, 0.0, 10.0, 12.0],
        )

        with connection.transaction():
            connection.execute(
                "delete from event_contract.roads where localid = %s", (second,)
            )

        assert _events(connection)[2] == (
            [second],
            ["delete"],
            4326,
            [4.0, 5.0, 4.0, 5.0],
        )

        try:
            with connection.transaction():
                connection.execute(
                    "insert into event_contract.roads (localid, shape) values "
                    "(gen_random_uuid(), ST_SetSRID(ST_Point(20, 20), 4326))"
                )
                raise RuntimeError("roll back")
        except RuntimeError:
            pass

        assert len(_events(connection)) == 3
    finally:
        connection.rollback()
        with connection.transaction():
            connection.execute("drop schema if exists event_contract cascade")
            connection.execute(
                "delete from geocomponents_event.change_outbox "
                "where dataset = 'event_contract'"
            )
        connection.close()
