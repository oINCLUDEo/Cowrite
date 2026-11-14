import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import httpx
import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError

from app.core.config import Settings
from app.core.db import get_session
from app.core.roles import RoleCache
from app.main import create_app
from app.modules.documents.service import require_role


async def test_role_cache_ttl_and_failure():
    redis = AsyncMock()
    cache = RoleCache(redis)
    user_id, document_id = uuid.uuid4(), uuid.uuid4()
    await cache.put(user_id, document_id, "editor")
    redis.set.assert_awaited_once_with(f"role:{user_id}:{document_id}", "editor", ex=60)
    redis.get.return_value = "viewer"
    assert await cache.get(user_id, document_id) == "viewer"
    await cache.invalidate(user_id, document_id)
    redis.delete.assert_awaited_once()
    redis.get.side_effect = redis.set.side_effect = redis.delete.side_effect = ConnectionError()
    assert await cache.get(user_id, document_id) is None
    await cache.put(user_id, document_id, "none")
    await cache.invalidate(user_id, document_id)


async def test_invalidation_waits_for_older_role_read():
    redis = AsyncMock()
    redis.get.return_value = None
    cache = RoleCache(redis)
    user_id, document_id = uuid.uuid4(), uuid.uuid4()
    started, release = asyncio.Event(), asyncio.Event()
    document = SimpleNamespace(owner_id=uuid.uuid4())

    async def stale_role(query):
        started.set()
        await release.wait()
        return "editor"

    session = Mock(info={"role_cache": cache})
    # Первый scalar возвращает документ; второй задерживает чтение старой роли.
    calls = 0

    async def scalar(query):
        nonlocal calls
        calls += 1
        return document if calls == 1 else await stale_role(query)

    session.scalar = AsyncMock(side_effect=scalar)
    lookup = asyncio.create_task(require_role(session, document_id, user_id))
    await started.wait()
    invalidation = asyncio.create_task(cache.invalidate(user_id, document_id))
    await asyncio.sleep(0)
    assert not invalidation.done()
    release.set()
    assert (await lookup)[1] == "editor"
    await invalidation
    assert redis.mock_calls[-2:] == [
        call.set(cache.key(user_id, document_id), "editor", ex=60),
        call.delete(cache.key(user_id, document_id)),
    ]


@pytest.mark.parametrize("new_role", [None, "viewer"])
async def test_redis_recovery_cannot_restore_revoked_editor_access(new_role):
    redis = AsyncMock()
    redis.get.return_value = "editor"
    cache = RoleCache(redis)
    user_id, document_id = uuid.uuid4(), uuid.uuid4()
    assert await cache.get(user_id, document_id) == "editor"
    redis.delete.side_effect = ConnectionError()
    await cache.invalidate(user_id, document_id)
    # Redis снова доступен, но неуспешный DELETE оставил в нём editor.
    redis.delete.side_effect = None
    session = Mock(info={"role_cache": cache})
    session.scalar = AsyncMock(side_effect=[SimpleNamespace(owner_id=uuid.uuid4()), new_role])
    with pytest.raises(HTTPException) as error:
        await require_role(session, document_id, user_id, "editor")
    assert error.value.status_code == 403
    assert session.scalar.await_count == 2
    assert redis.get.await_count == 1
    redis.set.assert_not_awaited()


async def test_role_cache_resumes_after_old_entries_expire(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.core.roles.monotonic", lambda: clock[0])
    redis = AsyncMock()
    cache = RoleCache(redis)
    user_id, document_id = uuid.uuid4(), uuid.uuid4()
    redis.delete.side_effect = ConnectionError()
    await cache.invalidate(user_id, document_id)
    clock[0] += 59
    assert await cache.get(user_id, document_id) is None
    await cache.put(user_id, document_id, "viewer")
    redis.get.assert_not_awaited()
    redis.set.assert_not_awaited()
    clock[0] += 2
    redis.get.return_value = None
    assert await cache.get(user_id, document_id) is None
    await cache.put(user_id, document_id, "viewer")
    redis.get.assert_awaited_once()
    redis.set.assert_awaited_once_with(cache.key(user_id, document_id), "viewer", ex=60)


async def test_request_id_body_limit_and_metrics():
    app = create_app(Settings(_env_file=None))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health", headers={"X-Request-ID": "request_123"})
        assert response.headers["x-request-id"] == "request_123"
        response = await client.get("/health", headers={"X-Request-ID": "unsafe space"})
        uuid.UUID(response.headers["x-request-id"])
        assert (
            await client.post("/auth/login", content=b"x" * (1024 * 1024 + 1))
        ).status_code == 413
        metrics = await client.get("/metrics")
        assert metrics.status_code == 200
        assert "http_requests_total" in metrics.text
        assert (await client.get("/health/live")).status_code == 200
        assert (await client.get("/health/ready")).status_code == 503


async def test_rate_limit_and_redis_outage():
    app = create_app(Settings(_env_file=None))

    async def session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = session
    redis = AsyncMock()
    app.state.redis = redis
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        redis.eval.return_value = [121, 30]
        response = await client.get("/documents")
        assert response.status_code == 429
        assert response.headers["retry-after"] == "30"
        redis.eval.side_effect = ConnectionError()
        assert (await client.post("/auth/login", json={})).status_code == 503
        assert (await client.get("/documents")).status_code == 401
