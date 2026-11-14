from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.models import User
from app.modules.auth.deps import get_github_client, get_oauth_store
from app.modules.auth.oauth_service import exchange, find_or_create_user, github_identity


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        jwt_secret=SecretStr("test-only-secret-with-at-least-32-bytes"),
        github_client_id="client",
        github_client_secret=SecretStr("secret"),
        github_redirect_uri="http://localhost:8080/api/auth/github/callback",
    )


@pytest.mark.parametrize("conflict", ["github", "email", "other"])
async def test_concurrent_account_creation(conflict):
    user = User(github_id=123, email="test@example.com", display_name="Test")
    session = MagicMock()
    session.scalar = AsyncMock(
        side_effect=[
            None,
            None,
            user if conflict == "github" else None,
            user if conflict == "email" else None,
        ]
    )
    session.commit = AsyncMock(side_effect=IntegrityError("INSERT", {}, Exception("constraint")))
    session.rollback = AsyncMock()
    if conflict == "github":
        assert await find_or_create_user(session, 123, "test@example.com", "Test") is user
    elif conflict == "email":
        with pytest.raises(HTTPException) as error:
            await find_or_create_user(session, 123, "test@example.com", "Test")
        assert error.value.status_code == 409
    else:
        with pytest.raises(IntegrityError):
            await find_or_create_user(session, 123, "test@example.com", "Test")
    session.rollback.assert_awaited_once()


async def test_exchange_requires_browser_before_consuming_code(settings):
    store = AsyncMock()
    with pytest.raises(HTTPException) as error:
        await exchange("code", None, settings, store, AsyncMock())
    assert error.value.status_code == 400
    store.take.assert_not_awaited()


async def test_github_rejects_invalid_email_list(settings):
    def respond(request):
        data = {
            "/login/oauth/access_token": {"access_token": "token"},
            "/user": {"id": 1, "login": "alice"},
            "/user/emails": {},
        }
        return httpx.Response(200, json=data[request.url.path])

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(HTTPException) as error:
            await github_identity("code", settings, client)
    assert error.value.status_code == 502


async def test_github_transport_timeout_is_controlled(settings):
    def timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(HTTPException) as error:
            await github_identity("code", settings, client)
    assert error.value.status_code == 502


async def test_http_client_and_redis_dependencies_close(settings):
    client_generator = get_github_client()
    client = await anext(client_generator)
    assert client.timeout.read == 10
    await client_generator.aclose()
    assert client.is_closed

    store_generator = get_oauth_store(settings)
    store = await anext(store_generator)
    assert store.redis.connection_pool.connection_kwargs["socket_timeout"] == 3
    await store_generator.aclose()
