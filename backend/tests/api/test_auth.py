import uuid

import jwt
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.security import create_access_token
from app.models import User

pytestmark = pytest.mark.integration
PAYLOAD = {"email": "Alice@example.com", "display_name": " Алиса ", "password": "long password 123"}


async def test_register_login_and_current_user(api_client, db_session):
    response = await api_client.post("/auth/register", json=PAYLOAD)
    assert response.status_code == 201
    user = response.json()
    assert user["email"] == "alice@example.com"
    assert user["display_name"] == "Алиса"
    assert "password_hash" not in user
    stored = await db_session.get(User, uuid.UUID(user["id"]))
    assert stored.password_hash.startswith("$argon2id$")
    assert PAYLOAD["password"] not in stored.password_hash

    response = await api_client.post(
        "/auth/login", json={"email": " ALICE@example.com ", "password": PAYLOAD["password"]}
    )
    assert response.status_code == 200
    token = response.json()
    assert token["expires_in"] == 1800
    assert token["token_type"] == "bearer"
    claims = jwt.decode(token["access_token"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 1800
    response = await api_client.get(
        "/users/me", headers={"Authorization": f"Bearer {token['access_token']}"}
    )
    assert response.json() == user


async def test_duplicate_email_returns_conflict(api_client):
    assert (await api_client.post("/auth/register", json=PAYLOAD)).status_code == 201
    response = await api_client.post(
        "/auth/register", json={**PAYLOAD, "email": "alice@example.com"}
    )
    assert response.status_code == 409


async def test_wrong_password_and_unknown_user_have_same_response(api_client):
    await api_client.post("/auth/register", json=PAYLOAD)
    first = await api_client.post(
        "/auth/login", json={"email": PAYLOAD["email"], "password": "wrong password 123"}
    )
    second = await api_client.post(
        "/auth/login", json={"email": "unknown@example.com", "password": "wrong password 123"}
    )
    assert first.status_code == second.status_code == 401
    assert first.json() == second.json()


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer broken"}, {"Authorization": "Basic abc"}]
)
async def test_me_rejects_missing_or_invalid_tokens(api_client, headers):
    response = await api_client.get("/users/me", headers=headers)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "updates",
    [
        {"password": "short"},
        {"password": "x" * 129},
        {"email": "not-email"},
        {"display_name": "   "},
        {"is_admin": True},
    ],
)
async def test_invalid_registration(api_client, updates):
    response = await api_client.post("/auth/register", json={**PAYLOAD, **updates})
    assert response.status_code == 422


async def test_token_for_nonexistent_user_is_rejected(api_client):
    settings = Settings(
        _env_file=None, jwt_secret=SecretStr("test-only-secret-with-at-least-32-bytes")
    )
    token = create_access_token(uuid.uuid4(), settings)
    response = await api_client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
