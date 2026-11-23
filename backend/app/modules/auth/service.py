"""Регистрация и вход: работа с БД, проверка пароля, выдача токена."""

from functools import lru_cache

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.auth.models import User
from app.modules.auth.schemas import Credentials, RegisterRequest, TokenResponse


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    # Для неизвестного email тоже проверяем хеш, чтобы не выдавать его быстрым ответом.
    return hash_password("not-a-real-user-password")


async def register(session: AsyncSession, data: RegisterRequest) -> User:
    # Argon2 нагружает CPU; выносим его из event loop, чтобы не тормозить другие запросы.
    user = User(
        email=str(data.email),
        display_name=data.display_name,
        password_hash=await run_in_threadpool(hash_password, data.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # Уникальный индекс защищает и от двух одновременных регистраций одного email.
        await session.rollback()
        if await session.scalar(select(User.id).where(User.email == str(data.email))) is not None:
            raise HTTPException(409, detail="Email is already registered") from None
        raise
    return user


async def login(session: AsyncSession, data: Credentials, settings: Settings) -> TokenResponse:
    user = await session.scalar(select(User).where(User.email == str(data.email)))
    encoded = (
        user.password_hash
        if user is not None and user.password_hash is not None
        else await run_in_threadpool(dummy_password_hash)
    )
    valid = await run_in_threadpool(verify_password, data.password, encoded)
    if user is None or user.password_hash is None or not valid:
        raise HTTPException(
            401, detail="Invalid email or password", headers={"WWW-Authenticate": "Bearer"}
        )
    return TokenResponse(access_token=create_access_token(user.id, settings))
