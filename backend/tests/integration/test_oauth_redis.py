import asyncio
import secrets

import pytest
from redis.asyncio import Redis

from app.core.config import Settings
from app.modules.auth.oauth_store import RedisOAuthStore, token_digest

pytestmark = pytest.mark.integration


async def test_real_redis_ttl_and_one_time_consumption(test_database_url):
    async with Redis.from_url(str(Settings().redis_cache_url), decode_responses=True) as redis:
        store = RedisOAuthStore(redis)
        tokens = {"state": secrets.token_urlsafe(32), "exchange": secrets.token_urlsafe(32)}
        keys = [f"oauth:{kind}:{token_digest(token)}" for kind, token in tokens.items()]
        try:
            for kind, ttl in (("state", 300), ("exchange", 60)):
                token = tokens[kind]
                await store.put(kind, token, {"browser": "hash"}, ttl)
                assert ttl - 2 <= await redis.ttl(f"oauth:{kind}:{token_digest(token)}") <= ttl
                results = await asyncio.gather(store.take(kind, token), store.take(kind, token))
                assert results.count({"browser": "hash"}) == 1
                assert results.count(None) == 1
        finally:
            await redis.delete(*keys)
