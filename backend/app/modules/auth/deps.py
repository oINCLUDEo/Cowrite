"""Зависимости роутеров: сессия БД, настройки и текущий пользователь."""

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_session
from app.core.security import decode_access_token
from app.modules.auth.models import User
from app.modules.auth.oauth_store import OAuthStore, RedisOAuthStore

# Формируем свой 401 и для отсутствующего токена, и для неверной схемы авторизации.
bearer = HTTPBearer(auto_error=False)
Session = Annotated[AsyncSession, Depends(get_session)]


def get_app_settings(request: Request) -> Settings:
    config: Settings = request.app.state.settings
    return config


AppSettings = Annotated[Settings, Depends(get_app_settings)]


async def get_oauth_store(settings: AppSettings) -> AsyncIterator[OAuthStore]:
    async with Redis.from_url(
        str(settings.redis_cache_url),
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    ) as redis:
        yield RedisOAuthStore(redis)


async def get_github_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=10) as client:
        yield client


OAuthStorage = Annotated[OAuthStore, Depends(get_oauth_store)]
GitHubClient = Annotated[httpx.AsyncClient, Depends(get_github_client)]


async def get_current_user(
    session: Session,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    error = HTTPException(
        401, detail="Invalid access token", headers={"WWW-Authenticate": "Bearer"}
    )
    if credentials is None:
        raise error
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except jwt.InvalidTokenError:
        raise error from None
    # Валидная подпись не гарантирует, что учётная запись ещё существует.
    user = await session.get(User, user_id)
    if user is None:
        raise error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
