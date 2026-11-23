"""Одноразовые OAuth-значения. В Redis хранятся хеши кодов, а не сами коды."""

import hashlib
import json
from typing import Protocol

from fastapi import HTTPException
from redis.asyncio import Redis
from redis.exceptions import RedisError


class OAuthStore(Protocol):
    async def put(self, kind: str, token: str, value: dict[str, str], ttl: int) -> None: ...

    async def take(self, kind: str, token: str) -> dict[str, str] | None: ...


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class RedisOAuthStore:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def put(self, kind: str, token: str, value: dict[str, str], ttl: int) -> None:
        try:
            await self.redis.set(f"oauth:{kind}:{token_digest(token)}", json.dumps(value), ex=ttl)
        except RedisError:
            raise HTTPException(503, detail="OAuth storage is unavailable") from None

    async def take(self, kind: str, token: str) -> dict[str, str] | None:
        try:
            # GETDEL атомарен: два запроса не смогут использовать один код.
            raw = await self.redis.getdel(f"oauth:{kind}:{token_digest(token)}")
        except RedisError:
            raise HTTPException(503, detail="OAuth storage is unavailable") from None
        if raw is None:
            return None
        try:
            value: object = json.loads(raw)
        except (ValueError, TypeError):
            raise HTTPException(503, detail="Invalid OAuth storage record") from None
        if not isinstance(value, dict) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in value.items()
        ):
            raise HTTPException(503, detail="Invalid OAuth storage record")
        return value
