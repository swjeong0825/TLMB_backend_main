from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config

HARDCODED_DATABASE_URL = "postgresql+asyncpg://@localhost:5432/tennis_league_integ"

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DATABASE_URL = os.getenv(
#     "DATABASE_URL",
#     config.get_main_option("sqlalchemy.url"),
# )
DATABASE_URL = HARDCODED_DATABASE_URL

from app.infrastructure.config.database import Base
from app.infrastructure.persistence.models.orm_models import (  # noqa: F401  # ensure models are imported
    LeagueORM,
    MatchORM,
    PlayerORM,
    TeamORM,
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(DATABASE_URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
