from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from starlette.requests import Request

from app.core.config import Settings
from app.core.db import Database, get_session
from app.main import create_app


async def test_database_closes_engine():
    database = Database(Settings(_env_file=None))
    with patch("sqlalchemy.ext.asyncio.AsyncEngine.dispose", new_callable=AsyncMock) as dispose:
        await database.close()
        dispose.assert_awaited_once()


async def test_lifespan_initializes_and_closes_database():
    app = create_app(Settings(_env_file=None))
    async with app.router.lifespan_context(app):
        assert isinstance(app.state.database, Database)
        app.state.database.close = AsyncMock()

    app.state.database.close.assert_awaited_once()


async def test_get_session_yields_and_closes_session():
    session = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = session
    database = SimpleNamespace(sessions=lambda: context)
    request = Request(
        {"type": "http", "app": SimpleNamespace(state=SimpleNamespace(database=database))}
    )

    yielded = [value async for value in get_session(request)]

    assert yielded == [session]
    context.__aexit__.assert_awaited_once()
