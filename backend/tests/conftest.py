"""Общие фикстуры: отдельная PostgreSQL-база, откат данных и API-клиент."""

import json
import os
import re
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
from jsonschema import Draft202012Validator
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.contracts import CONTRACT
from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = Settings().test_database_url
    if url is None:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    if not url.path or not url.path.endswith("_test"):
        # Защита от случайного запуска тестов на базе с рабочими документами.
        pytest.fail("TEST_DATABASE_URL must point to a dedicated database ending in _test")
    env = {**os.environ, "DATABASE_URL": str(url)}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return str(url)


@pytest.fixture
async def db_session(test_database_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(test_database_url)
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            # Commit внутри сервиса закрывает savepoint, но не внешнюю транзакцию теста.
            async with AsyncSession(
                bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
            ) as session:
                yield session
            await transaction.rollback()
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def notification_queue(monkeypatch):
    from app.worker import invite

    queue = MagicMock()
    monkeypatch.setattr(invite, "apply_async", queue)
    return queue


@pytest.fixture
async def api_client(db_session, notification_queue):
    settings = Settings(
        _env_file=None, jwt_secret=SecretStr("test-only-secret-with-at-least-32-bytes")
    )
    app = create_app(settings)

    async def override_session():
        yield db_session

    app.dependency_overrides[get_session] = override_session
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    async def validate_response(response: httpx.Response) -> None:
        await response.aread()
        for template, methods in contract["paths"].items():
            if not re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", template), response.request.url.path):
                continue
            operation = methods[response.request.method.lower()]
            declared = operation["responses"].get(str(response.status_code))
            assert declared is not None, (template, response.status_code)
            if response.status_code == 204:
                assert response.content == b"", template
                return
            if response.headers.get("content-type", "").startswith("application/json"):
                schema = declared["content"]["application/json"]["schema"]
                Draft202012Validator({**schema, "components": contract["components"]}).validate(
                    response.json()
                )
            return
        pytest.fail(f"Response path absent from OpenAPI: {response.request.url.path}")

    # Запросы идут через настоящий роутер, но используют откатываемую тестовую сессию.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        event_hooks={"response": [validate_response]},
    ) as client:
        yield client
