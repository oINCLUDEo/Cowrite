"""Пул подключений, сессия на запрос и общая база SQLAlchemy-моделей."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings


class Base(DeclarativeBase):
    # Одинаковые имена ограничений нужны для предсказуемых миграций Alembic.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = create_async_engine(str(settings.database_url), pool_pre_ping=True)
        # После commit поля объекта остаются доступны без повторного SQL-запроса.
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self) -> None:
        await self.engine.dispose()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    # Сессия закрывается после запроса. Решение о commit принимает сервисный слой.
    database: Database = request.app.state.database
    async with database.sessions() as session:
        session.info["role_cache"] = getattr(request.app.state, "role_cache", None)
        yield session
