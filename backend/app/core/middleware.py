"""Ограничения запросов, request_id и структурированные журналы без тел и токенов."""

import re
import time
import uuid
from typing import Any

import structlog
from redis.exceptions import RedisError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = structlog.get_logger()
RATE_SCRIPT = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('EXPIRE', KEYS[1], 60) end
return {n, redis.call('TTL', KEYS[1])}
"""


class RequestMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        request_id = headers.get(b"x-request-id", b"").decode("ascii", "ignore")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id):
            request_id = str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.monotonic()
        status = 500

        async def send_with_id(message: Any) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"].append((b"x-request-id", request_id.encode()))
            await send(message)

        path = scope["path"]
        app = scope.get("app")
        redis = getattr(app.state, "redis", None) if app else None
        auth = any(
            path.endswith(p)
            for p in (
                "/auth/register",
                "/auth/login",
                "/auth/exchange",
                "/auth/github/login",
                "/auth/github/callback",
            )
        )
        background = path.endswith("/export") or (
            path.endswith("/members") and scope["method"] == "POST"
        )
        try:
            if redis is not None and path not in (
                "/health",
                "/health/live",
                "/health/ready",
                "/metrics",
            ):
                ip = (scope.get("client") or ("unknown",))[0]
                # Внешний IP выставляет только наш Nginx; прямой API привязан к loopback.
                limits = [("all", 120)] + ([("auth", 10)] if auth else [])
                for suffix, limit in limits:
                    count, ttl = await redis.eval(RATE_SCRIPT, 1, f"rate:{ip}:{suffix}")
                    if count > limit:
                        await JSONResponse(
                            {
                                "detail": {
                                    "code": "rate_limited",
                                    "message": "Слишком много запросов",
                                }
                            },
                            429,
                            headers={"Retry-After": str(max(1, ttl))},
                        )(scope, receive, send_with_id)
                        return
        except RedisError as error:
            logger.warning("redis_request_failed", error_type=type(error).__name__)
            if auth or background:
                await JSONResponse(
                    {
                        "detail": {
                            "code": "redis_unavailable",
                            "message": "Сервис временно недоступен",
                        }
                    },
                    503,
                )(scope, receive, send_with_id)
                return
        # Читаем ограниченный буфер до вызова роутера, включая chunked запросы.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 1024 * 1024:
                await JSONResponse(
                    {
                        "detail": {
                            "code": "body_too_large",
                            "message": "Тело запроса слишком велико",
                        }
                    },
                    413,
                )(scope, receive, send_with_id)
                return
            if not message.get("more_body", False):
                break
        consumed = False

        async def buffered_receive() -> Any:
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        try:
            await self.app(scope, buffered_receive, send_with_id)
        finally:
            logger.info(
                "http_request",
                service="api",
                request_id=request_id,
                method=scope["method"],
                status=status,
                duration_ms=round((time.monotonic() - start) * 1000, 2),
            )
