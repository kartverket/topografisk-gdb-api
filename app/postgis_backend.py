from pathlib import Path

from psycopg import Connection


class PostGISBackend:
    @staticmethod
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
