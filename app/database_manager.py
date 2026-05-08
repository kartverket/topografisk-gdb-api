from pathlib import Path
from typing import cast

from fastapi import Request
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


def get_db_connection_pool(connection_url: str):
    return AsyncConnectionPool(
        connection_url,
        min_size=1,
        max_size=10,
        open=False,
        kwargs={"row_factory": dict_row},
    )


async def get_db_conn(request: Request):
    connection_pool = cast(AsyncConnectionPool, request.state.connection_pool)
    async with connection_pool.connection() as conn:
        yield conn


async def initialize_schema(conn: Connection) -> None:
    base_path = Path("app") / "sql"

    # TODO: add nibio db_schema initialisation here.
    # current file (ar5_db_nibio.sql) is a pg_dump and
    # TODO: Decide if files should stay here or somewhere else
    # If here we can loop through and execute using Path().glob()
    # Only thing to be aware is that "fkb_felles" should run first
    # in current setup. glob(".sql") would give wrong order but
    # a rename to "01_fkb_felles.sql", "02_..." would work
    for file in ("fkb_felles", "fkb_bane", "fkb_ar5"):  # fkb_felles first
        await conn.execute(
            (base_path / file).with_suffix(".sql").read_text(encoding="utf-8")
        )
