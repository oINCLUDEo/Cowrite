"""HTTP-маршруты входа и регистрации. Запросы к БД выполняются в service.py."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.modules.auth import oauth_service, service
from app.modules.auth.deps import AppSettings, CurrentUser, GitHubClient, OAuthStorage, Session
from app.modules.auth.schemas import (
    Credentials,
    ExchangeRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(tags=["auth"])
BrowserCookie = Annotated[str | None, Cookie(alias="cowrite_oauth_browser", max_length=128)]


@router.post("/auth/register", response_model=UserResponse, status_code=201)
async def register(data: RegisterRequest, session: Session) -> UserResponse:
    return UserResponse.model_validate(await service.register(session, data))


@router.post("/auth/login", response_model=TokenResponse)
async def login(data: Credentials, session: Session, settings: AppSettings) -> TokenResponse:
    return await service.login(session, data, settings)


@router.get("/users/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get("/auth/github/login", status_code=302)
async def github_login(
    settings: AppSettings, store: OAuthStorage, request: Request
) -> RedirectResponse:
    url, browser = await oauth_service.start(settings, store)
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        "cowrite_oauth_browser",
        browser,
        max_age=300,
        httponly=True,
        samesite="lax",
        secure=settings.github_redirect_uri is not None
        and settings.github_redirect_uri.scheme == "https",
        path=f"{request.scope.get('root_path', '')}/auth",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/auth/github/callback", status_code=302)
async def github_callback(
    settings: AppSettings,
    store: OAuthStorage,
    client: GitHubClient,
    session: Session,
    request: Request,
    code: Annotated[str, Query(min_length=1, max_length=512)],
    state: Annotated[str, Query(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")],
    browser: BrowserCookie = None,
) -> RedirectResponse:
    url = await oauth_service.callback(code, state, browser, settings, store, client, session)
    response = RedirectResponse(
        url,
        status_code=302,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
    # OAuth мог занять почти пять минут; даём cookie ещё минуту на обмен кода.
    assert browser is not None
    response.set_cookie(
        "cowrite_oauth_browser",
        browser,
        max_age=60,
        httponly=True,
        samesite="lax",
        secure=settings.github_redirect_uri is not None
        and settings.github_redirect_uri.scheme == "https",
        path=f"{request.scope.get('root_path', '')}/auth",
    )
    return response


@router.post("/auth/exchange", response_model=TokenResponse)
async def exchange_code(
    data: ExchangeRequest,
    settings: AppSettings,
    store: OAuthStorage,
    session: Session,
    response: Response,
    request: Request,
    browser: BrowserCookie = None,
) -> TokenResponse:
    token = await oauth_service.exchange(data.code, browser, settings, store, session)
    response.delete_cookie(
        "cowrite_oauth_browser", path=f"{request.scope.get('root_path', '')}/auth"
    )
    response.headers["Cache-Control"] = "no-store"
    return token
