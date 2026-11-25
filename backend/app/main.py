"""Точка входа API: создание приложения, подключение роутеров и общих ресурсов."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.core.db import Database
from app.core.logging import configure_log_redaction
from app.core.metrics import MetricsMiddleware
from app.core.middleware import RequestMiddleware
from app.core.roles import RoleCache
from app.core.schemas import ErrorResponse, error_response
from app.modules.auth.router import router as auth_router
from app.modules.collab.rooms import RoomManager
from app.modules.collab.router import router as collaboration_router
from app.modules.documents.router import router as documents_router
from app.modules.exports.router import router as exports_router
from app.modules.versions.router import router as versions_router


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_log_redaction()
    # В тестах передаём отдельные настройки, при обычном запуске читаем окружение.
    config = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # Пул БД и CRDT-комнаты живут столько же, сколько процесс API.
        database = Database(config)
        application.state.database = database
        redis = Redis.from_url(
            str(config.redis_cache_url),
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        application.state.redis = redis
        application.state.role_cache = RoleCache(redis)
        manager = RoomManager(database, config)
        application.state.rooms = manager
        await manager.start()
        try:
            yield
        finally:
            await manager.stop()
            # Закрываем соединения с БД даже при ошибке внутри приложения.
            await database.close()
            await redis.aclose()

    application = FastAPI(
        title=config.app_name,
        version="0.1.0",
        debug=config.debug,
        lifespan=lifespan,
        root_path=config.api_root_path,
        description=(
            "REST API платформы совместного редактирования. "
            "Аутентификация — JWT Bearer (кроме `/auth/register`, `/auth/login` и "
            "OAuth-редиректов). Формат ошибок единый: "
            '`{"detail": {"code": "...", "message": "..."}}`. '
            "Все запросы ограничены по IP: 120/мин, для входа — 10/мин; "
            "ответ 429 содержит `Retry-After`. "
            "Совместное редактирование работает по отдельному бинарному "
            "WebSocket-протоколу, описанному в `docs/websocket.md`."
        ),
        openapi_tags=[
            {"name": "auth", "description": "Регистрация, вход по паролю и через GitHub."},
            {"name": "documents", "description": "Документы, роли и участники."},
            {"name": "versions", "description": "Снапшоты состояния и откат."},
            {"name": "exports", "description": "Фоновый экспорт в PDF."},
            {"name": "health", "description": "Проверки процесса и зависимостей."},
        ],
        responses={
            code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409, 429, 502, 503)
        },
    )
    application.include_router(collaboration_router)
    application.state.settings = config
    application.include_router(auth_router)
    application.include_router(documents_router)
    application.include_router(versions_router)
    application.include_router(exports_router)
    application.add_middleware(RequestMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.allowed_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    application.add_middleware(MetricsMiddleware, excluded_handlers=["/metrics"])
    Instrumentator().expose(application, include_in_schema=False)

    @application.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        detail: object = error.detail
        if isinstance(detail, str):
            codes = {
                401: "unauthorized",
                403: "access_denied",
                404: "not_found",
                409: "conflict",
                503: "service_unavailable",
            }
            detail = {"code": codes.get(error.status_code, "request_failed"), "message": detail}
        return JSONResponse(
            {"detail": detail}, status_code=error.status_code, headers=error.headers
        )

    @application.get(
        "/health/live",
        response_model=HealthResponse,
        tags=["health"],
        summary="Жив ли процесс",
        description=(
            "Возвращает 200, если процесс API обрабатывает запросы. "
            "Зависимости не проверяются, аутентификация не требуется."
        ),
    )
    async def live() -> HealthResponse:
        return HealthResponse()

    @application.get(
        "/health/ready",
        response_model=HealthResponse,
        tags=["health"],
        summary="Готов ли сервис к приёму трафика",
        description=(
            "Выполняет `SELECT 1` в PostgreSQL и `PING` в Redis. "
            "При недоступности любой зависимости возвращает 503."
        ),
        responses={503: error_response("PostgreSQL или Redis недоступны.")},
    )
    async def ready(request: Request) -> HealthResponse:
        try:
            async with request.app.state.database.sessions() as session:
                await session.execute(text("SELECT 1"))
            await request.app.state.redis.ping()
        except Exception:
            raise HTTPException(503, detail="Dependencies unavailable") from None
        return HealthResponse()

    @application.get(
        "/health",
        response_model=HealthResponse,
        tags=["health"],
        summary="Базовая проверка доступности",
        description="Проверка процесса API. Доступность PostgreSQL и Redis здесь не проверяется.",
    )
    async def health() -> HealthResponse:
        return HealthResponse()

    return application


app = create_app()
