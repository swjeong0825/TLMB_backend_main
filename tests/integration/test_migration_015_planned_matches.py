import os
from pathlib import Path
import subprocess
import sys
from sqlalchemy import inspect, text


async def test_migration_upgrade_downgrade_and_three_column_schema(session_factory):
    # Use the CLI so the repo's alembic/ package cannot shadow the installed library.
    environment = dict(os.environ, DATABASE_URL=session_factory.kw["bind"].url.render_as_string(hide_password=False))

    def migrate(*args):
        subprocess.run(
            [sys.executable, str(Path(sys.executable).with_name("alembic")), *args],
            cwd=Path(__file__).resolve().parents[2], env=environment,
            check=True, capture_output=True, text=True,
        )

    try:
        migrate("downgrade", "014")
        async with session_factory() as session:
            assert await session.scalar(text("SELECT to_regclass('public.planned_matches')")) is None
    finally:
        migrate("upgrade", "head")

    async with session_factory() as session:
        connection = await session.connection()

        def check_shape(sync_connection):
            inspector = inspect(sync_connection)
            columns = inspector.get_columns("planned_matches")
            assert [column["name"] for column in columns] == ["league_id", "id", "value"]
            assert all(not column["nullable"] and column["default"] is None for column in columns)
            assert inspector.get_pk_constraint("planned_matches")["constrained_columns"] == ["league_id", "id"]
            assert inspector.get_foreign_keys("planned_matches")[0]["options"]["ondelete"] == "CASCADE"

        await connection.run_sync(check_shape)
