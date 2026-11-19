"""Хеширование паролей и выпуск JWT. Проверка пользователя в БД — в auth/deps.py."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException

from app.core.config import Settings

# Параметры Argon2id из ТЗ: 64 MiB памяти и три прохода.
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def signing_secret(settings: Settings) -> str:
    # Без настроенного ключа вход недоступен; случайный ключ на старте не создаём.
    if settings.jwt_secret is None:
        raise HTTPException(503, detail="Authentication is not configured")
    return settings.jwt_secret.get_secret_value()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID, settings: Settings) -> str:
    # В токене только идентификатор пользователя, без пароля и ролей документов.
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": now,
            "exp": now + timedelta(minutes=30),
            "jti": str(uuid.uuid4()),
            "iss": "cowrite",
            "aud": "cowrite-api",
        },
        signing_secret(settings),
        algorithm="HS256",
    )


def decode_access_token(token: str, settings: Settings) -> uuid.UUID:
    # Алгоритм задаём сами. Значению alg из входящего токена не доверяем.
    payload = jwt.decode(
        token,
        signing_secret(settings),
        algorithms=["HS256"],
        issuer="cowrite",
        audience="cowrite-api",
        leeway=30,
        options={"require": ["sub", "iat", "exp", "jti", "iss", "aud"]},
    )
    try:
        return uuid.UUID(payload["sub"])
    except (ValueError, TypeError, AttributeError) as error:
        raise jwt.InvalidTokenError("Invalid subject") from error
