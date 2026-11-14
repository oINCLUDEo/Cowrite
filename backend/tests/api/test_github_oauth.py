import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.db import get_session
from app.main import create_app
from app.models import User
from app.modules.auth.deps import get_github_client, get_oauth_store
from app.modules.auth.oauth_store import token_digest

pytestmark = pytest.mark.integration


class MemoryStore:
    def __init__(self):
        self.records = {}

    async def put(self, kind, token, value, ttl):
        self.records[(kind, token_digest(token))] = (value, time.monotonic() + ttl)

    async def take(self, kind, token):
        record = self.records.pop((kind, token_digest(token)), None)
        return record[0] if record and record[1] > time.monotonic() else None


@pytest.fixture
async def oauth(db_session):
    settings = Settings(
        _env_file=None,
        jwt_secret=SecretStr("test-only-secret-with-at-least-32-bytes"),
        github_client_id="test-client",
        github_client_secret=SecretStr("test-secret"),
        github_redirect_uri="https://test/api/auth/github/callback",
        frontend_url="https://test",
        api_root_path="/api",
    )
    store = MemoryStore()
    behavior = {"verified": True, "status": 200, "invalid": False, "token_error": False}
    requests = []

    def github(request):
        requests.append(request)
        if behavior["status"] != 200:
            return httpx.Response(behavior["status"])
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(
                200,
                json={} if behavior["token_error"] else {"access_token": "github-private-token"},
            )
        assert request.headers["Authorization"] == "Bearer github-private-token"
        if request.url.path == "/user":
            return httpx.Response(
                200,
                json={}
                if behavior["invalid"]
                else {"id": 12345, "login": "alice", "name": "Алиса"},
            )
        assert request.url.path == "/user/emails"
        return httpx.Response(
            200,
            json=[
                {"email": "alice@example.com", "primary": True, "verified": behavior["verified"]}
            ],
        )

    app = create_app(settings)

    async def session_override():
        yield db_session

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(github), timeout=10
    ) as github_client:
        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[get_oauth_store] = lambda: store
        app.dependency_overrides[get_github_client] = lambda: github_client
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://test"
        ) as client:
            yield client, store, behavior, requests


async def begin(client):
    response = await client.get("/api/auth/github/login")
    assert response.status_code == 302
    location = urlsplit(response.headers["location"])
    assert location.netloc == "github.com"
    query = parse_qs(location.query)
    assert query["scope"] == ["user:email"]
    assert query["redirect_uri"] == ["https://test/api/auth/github/callback"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    return query["state"][0]


async def complete(client, state):
    return await client.get(
        "/api/auth/github/callback", params={"code": "github-code", "state": state}
    )


async def test_github_login_exchange_and_existing_account(oauth, db_session):
    client, store, _, requests = oauth
    state = await begin(client)
    state_record = store.records[("state", token_digest(state))]
    assert 298 < state_record[1] - time.monotonic() <= 300
    response = await complete(client, state)
    assert response.status_code == 302
    location = response.headers["location"]
    assert "Max-Age=60" in response.headers["set-cookie"]
    assert location.startswith("https://test/auth/callback#code=")
    assert "github-private-token" not in location
    code = parse_qs(urlsplit(location).fragment)["code"][0]
    assert 58 < store.records[("exchange", token_digest(code))][1] - time.monotonic() <= 60
    response = await client.post("/api/auth/exchange", json={"code": code})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    token = response.json()["access_token"]
    me = await client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["email"] == "alice@example.com"
    user = await db_session.scalar(select(User).where(User.github_id == 12345))
    assert user.password_hash is None
    assert not hasattr(user, "access_token")
    assert len(requests) == 3
    assert (await complete(client, state)).status_code == 400
    # Повторный вход находит пользователя по GitHub ID, не создаёт дубликат.
    assert (await complete(client, await begin(client))).status_code == 302
    assert (
        await db_session.scalar(
            select(func.count()).select_from(User).where(User.github_id == 12345)
        )
        == 1
    )


async def test_exchange_code_cannot_be_reused(oauth):
    client, _, _, _ = oauth
    response = await complete(client, await begin(client))
    code = parse_qs(urlsplit(response.headers["location"]).fragment)["code"][0]
    assert (await client.post("/api/auth/exchange", json={"code": code})).status_code == 200
    await begin(client)  # Новая cookie не делает старый код действительным.
    assert (await client.post("/api/auth/exchange", json={"code": code})).status_code == 400


@pytest.mark.parametrize("mode", ["wrong-state", "missing-cookie", "wrong-cookie", "expired"])
async def test_invalid_state_is_rejected_before_github(oauth, mode):
    client, store, _, requests = oauth
    state = await begin(client)
    if mode == "wrong-state":
        state = "x" * 43
    elif mode == "missing-cookie":
        client.cookies.clear()
    elif mode == "wrong-cookie":
        client.cookies.clear()
        client.cookies.set("cowrite_oauth_browser", "wrong", path="/api/auth")
    else:
        key = ("state", token_digest(state))
        store.records[key] = (store.records[key][0], 0)
    assert (await complete(client, state)).status_code == 400
    assert not requests


async def test_local_email_is_not_automatically_linked(oauth, db_session):
    db_session.add(User(email="alice@example.com", display_name="Local", password_hash="hash"))
    await db_session.flush()
    client, _, _, _ = oauth
    response = await complete(client, await begin(client))
    assert response.status_code == 409
    assert (
        await db_session.scalar(select(User.github_id).where(User.email == "alice@example.com"))
        is None
    )


@pytest.mark.parametrize(
    "mode,expected", [("verified", 400), ("status", 502), ("invalid", 502), ("token_error", 400)]
)
async def test_github_errors(oauth, mode, expected):
    client, _, behavior, _ = oauth
    behavior[mode] = 503 if mode == "status" else mode != "verified"
    assert (await complete(client, await begin(client))).status_code == expected


@pytest.mark.parametrize("mode", ["expired", "wrong-cookie", "deleted-user"])
async def test_exchange_rejects_invalid_context(oauth, db_session, mode):
    client, store, _, _ = oauth
    response = await complete(client, await begin(client))
    code = parse_qs(urlsplit(response.headers["location"]).fragment)["code"][0]
    if mode == "expired":
        key = ("exchange", token_digest(code))
        store.records[key] = (store.records[key][0], 0)
    elif mode == "wrong-cookie":
        await begin(client)
    else:
        user = await db_session.scalar(select(User).where(User.github_id == 12345))
        await db_session.delete(user)
        await db_session.flush()
    response = await client.post("/api/auth/exchange", json={"code": code})
    assert response.status_code == (401 if mode == "deleted-user" else 400)


async def test_unconfigured_github_returns_503(api_client):
    response = await api_client.get("/auth/github/login")
    assert response.status_code == 503
