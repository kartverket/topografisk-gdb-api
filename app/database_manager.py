from typing import cast

from fastapi import Request
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
