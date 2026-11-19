import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


@pytest.fixture
def settings():
    return Settings(_env_file=None, jwt_secret=SecretStr("test-only-secret-with-at-least-32-bytes"))


def test_password_hash_and_verification():
    encoded = hash_password("long password 123")
    assert encoded.startswith("$argon2id$")
    assert verify_password("long password 123", encoded)
    assert not verify_password("wrong password", encoded)
    assert not verify_password("password", "invalid hash")


def test_token_roundtrip(settings):
    user_id = uuid.uuid4()
    assert decode_access_token(create_access_token(user_id, settings), settings) == user_id


@pytest.mark.parametrize(
    "change",
    [
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"aud": "another-api"},
        {"iss": "attacker"},
        {"sub": "not-uuid"},
    ],
)
def test_token_rejects_invalid_claims(settings, change):
    token = create_access_token(uuid.uuid4(), settings)
    payload = jwt.decode(token, options={"verify_signature": False})
    payload.update(change)
    forged = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(forged, settings)


def test_token_rejects_wrong_signature(settings):
    other = Settings(_env_file=None, jwt_secret=SecretStr("another-test-secret-with-32-plus-bytes"))
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(create_access_token(uuid.uuid4(), other), settings)


def test_auth_without_secret_is_unavailable():
    with pytest.raises(HTTPException) as error:
        create_access_token(uuid.uuid4(), Settings(_env_file=None))
    assert error.value.status_code == 503
