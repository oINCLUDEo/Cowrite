from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError

from app.modules.auth.oauth_store import RedisOAuthStore, token_digest


async def test_store_uses_hashed_keys_ttl_and_atomic_getdel():
    redis = AsyncMock()
    store = RedisOAuthStore(redis)
    await store.put("state", "secret-code", {"browser": "hash"}, ttl=300)
    redis.set.assert_awaited_once_with(
        f"oauth:state:{token_digest('secret-code')}", '{"browser": "hash"}', ex=300
    )
    redis.getdel.return_value = '{"browser": "hash"}'
    assert await store.take("state", "secret-code") == {"browser": "hash"}
    redis.getdel.assert_awaited_once_with(f"oauth:state:{token_digest('secret-code')}")
    redis.getdel.return_value = None
    assert await store.take("state", "missing") is None


@pytest.mark.parametrize("operation", ["put", "take"])
async def test_redis_failure_is_controlled(operation):
    redis = AsyncMock()
    redis.set.side_effect = redis.getdel.side_effect = ConnectionError("offline")
    store = RedisOAuthStore(redis)
    with pytest.raises(HTTPException) as error:
        if operation == "put":
            await store.put("state", "code", {}, 300)
        else:
            await store.take("state", "code")
    assert error.value.status_code == 503


@pytest.mark.parametrize("raw", ['{"browser": 1}', "[]", "bad-json"])
async def test_invalid_storage_record_is_controlled(raw):
    redis = AsyncMock()
    redis.getdel.return_value = raw
    with pytest.raises(HTTPException) as error:
        await RedisOAuthStore(redis).take("state", "code")
    assert error.value.status_code == 503
