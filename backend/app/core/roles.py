"""Redis — только ускорение чтения ролей. Источник истины остаётся в PostgreSQL."""

import asyncio
import uuid
from time import monotonic
from weakref import WeakValueDictionary

from redis.asyncio import Redis
from redis.exceptions import RedisError

ROLE_TTL = 60


class RoleCache:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self._locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
        self._bypass_until = 0.0

    def lock(self, user_id: uuid.UUID, document_id: uuid.UUID) -> asyncio.Lock:
        # В единственном API-процессе позднее чтение не вернёт в кэш старую роль
        # после инвалидации. Неактивные пары не удерживаются в памяти.
        key = self.key(user_id, document_id)
        if (lock := self._locks.get(key)) is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    def key(self, user_id: uuid.UUID, document_id: uuid.UUID) -> str:
        return f"role:{user_id}:{document_id}"

    async def get(self, user_id: uuid.UUID, document_id: uuid.UUID) -> str | None:
        if monotonic() < self._bypass_until:
            return None
        try:
            value = await self.redis.get(self.key(user_id, document_id))
            return value if isinstance(value, str) else None
        except RedisError:
            return None

    async def put(self, user_id: uuid.UUID, document_id: uuid.UUID, role: str) -> None:
        if monotonic() < self._bypass_until:
            return
        try:
            await self.redis.set(self.key(user_id, document_id), role, ex=ROLE_TTL)
        except RedisError:
            pass

    async def invalidate(self, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        async with self.lock(user_id, document_id):
            try:
                await self.redis.delete(self.key(user_id, document_id))
            except RedisError:
                # После восстановления Redis там может остаться отозванная роль.
                # До истечения TTL всех старых записей читаем только PostgreSQL.
                self._bypass_until = monotonic() + ROLE_TTL
