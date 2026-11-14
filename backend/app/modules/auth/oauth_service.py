"""GitHub OAuth: state, проверка профиля и обмен короткого кода на JWT."""

import secrets
import uuid
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import create_access_token, signing_secret
from app.modules.auth.models import User
from app.modules.auth.oauth_store import OAuthStore, token_digest
from app.modules.auth.schemas import GitHubEmail, GitHubProfile, TokenResponse


def require_github(settings: Settings) -> None:
    if not (
        settings.github_client_id and settings.github_client_secret and settings.github_redirect_uri
    ):
        raise HTTPException(503, detail="GitHub login is not configured")
    signing_secret(settings)


async def start(settings: Settings, store: OAuthStore) -> tuple[str, str]:
    require_github(settings)
    state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    await store.put("state", state, {"browser": token_digest(browser)}, ttl=300)
    query = urlencode(
        {
            "client_id": settings.github_client_id,
            "redirect_uri": str(settings.github_redirect_uri),
            "scope": "user:email",
            "state": state,
        }
    )
    return f"https://github.com/login/oauth/authorize?{query}", browser


async def github_identity(
    code: str, settings: Settings, client: httpx.AsyncClient
) -> tuple[int, str, str]:
    require_github(settings)
    assert settings.github_client_secret is not None
    try:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret.get_secret_value(),
                "code": code,
                "redirect_uri": str(settings.github_redirect_uri),
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        token_data = token_response.json()
        token = token_data.get("access_token") if isinstance(token_data, dict) else None
        if not isinstance(token, str) or not token:
            raise HTTPException(400, detail="GitHub rejected the authorization code")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        profile_response = await client.get("https://api.github.com/user", headers=headers)
        profile_response.raise_for_status()
        emails_response = await client.get("https://api.github.com/user/emails", headers=headers)
        emails_response.raise_for_status()
        profile = GitHubProfile.model_validate(profile_response.json())
        emails = emails_response.json()
        if not isinstance(emails, list):
            raise ValueError("Invalid email list")
        addresses = [GitHubEmail.model_validate(item) for item in emails]
    except httpx.HTTPError:
        raise HTTPException(502, detail="GitHub is unavailable") from None
    except (ValueError, ValidationError):
        raise HTTPException(502, detail="Invalid response from GitHub") from None
    primary = next((item for item in addresses if item.primary and item.verified), None)
    if primary is None:
        raise HTTPException(400, detail="GitHub has no verified primary email")
    name = (profile.name or "").strip() or profile.login
    return profile.id, str(primary.email).lower(), name[:80]


async def find_or_create_user(
    session: AsyncSession, github_id: int, email: str, display_name: str
) -> User:
    user = await session.scalar(select(User).where(User.github_id == github_id))
    if user is not None:
        return user
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(
            409, detail="Email already registered; sign in with your existing account"
        )
    user = User(github_id=github_id, email=email, display_name=display_name)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # Другой браузер мог завершить вход в ту же учётную запись раньше нас.
        concurrent = await session.scalar(select(User).where(User.github_id == github_id))
        if concurrent is not None:
            return concurrent
        if await session.scalar(select(User).where(User.email == email)) is not None:
            raise HTTPException(
                409, detail="Email already registered; sign in with your existing account"
            ) from None
        raise
    return user


async def callback(
    code: str,
    state: str,
    browser: str | None,
    settings: Settings,
    store: OAuthStore,
    client: httpx.AsyncClient,
    session: AsyncSession,
) -> str:
    if not browser:
        raise HTTPException(400, detail="Missing OAuth browser cookie")
    record = await store.take("state", state)
    if record is None or not secrets.compare_digest(
        record.get("browser", ""), token_digest(browser)
    ):
        raise HTTPException(400, detail="Invalid or expired OAuth state")
    github_id, email, name = await github_identity(code, settings, client)
    user = await find_or_create_user(session, github_id, email, name)
    exchange_code = secrets.token_urlsafe(32)
    await store.put(
        "exchange",
        exchange_code,
        {"user_id": str(user.id), "browser": token_digest(browser)},
        ttl=60,
    )
    # Во фронтенд уходит только короткий код; токена GitHub и JWT в URL нет.
    return f"{str(settings.frontend_url).rstrip('/')}/auth/callback#code={exchange_code}"


async def exchange(
    code: str, browser: str | None, settings: Settings, store: OAuthStore, session: AsyncSession
) -> TokenResponse:
    signing_secret(settings)
    if not browser:
        raise HTTPException(400, detail="Missing OAuth browser cookie")
    record = await store.take("exchange", code)
    if record is None or not secrets.compare_digest(
        record.get("browser", ""), token_digest(browser)
    ):
        raise HTTPException(400, detail="Invalid or expired exchange code")
    user = await session.get(User, uuid.UUID(record["user_id"]))
    if user is None:
        raise HTTPException(401, detail="User no longer exists")
    return TokenResponse(access_token=create_access_token(user.id, settings))
