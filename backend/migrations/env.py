"""Запуск миграций с настройками приложения и асинхронным драйвером PostgreSQL."""

import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app import models  # noqa: F401 — регистрация таблиц в Base.metadata
from app.core.config import get_settings
from app.core.db import Base

target_metadata = Base.metadata


def configure(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    # Миграция — разовый процесс: держать пул соединений после неё не нужно.
    engine = create_async_engine(str(get_settings().database_url), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(configure)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(
        url=str(get_settings().database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
