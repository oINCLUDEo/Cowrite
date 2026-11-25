"""HTTP-маршруты входа и регистрации. Запросы к БД выполняются в service.py."""

from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.core.schemas import error_response
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

# Общие тексты ошибок: используются в нескольких маршрутах.
# Код 422 не переопределяем: его схему HTTPValidationError генерирует FastAPI.
RATE_LIMIT = "Слишком много запросов. Лимит на IP: 120/мин, для входа — 10/мин."
RATE_LIMIT_HEADER = f"{RATE_LIMIT} Ответ содержит заголовок Retry-After в секундах."
BAD_BODY = "Тело запроса не соответствует схеме или превышает 1 MiB (413)."
UNAUTHORIZED = "Access-токен не передан, истёк или невалиден."

USER_ERRORS: dict[int | str, dict[str, Any]] = {
    400: error_response(BAD_BODY),
    409: error_response("Пользователь с таким email уже зарегистрирован."),
    429: error_response(RATE_LIMIT_HEADER),
}


@router.post(
    "/auth/register",
    response_model=UserResponse,
    status_code=201,
    summary="Регистрация по email",
    description=(
        "Создаёт пользователя с email и паролем длиной 12–128 символов. "
        "Email приводится к нижнему регистру. Токен не выдаётся — вызовите /auth/login. "
        "Ответ не содержит хеш пароля."
    ),
    responses={**USER_ERRORS},
)
async def register(data: RegisterRequest, session: Session) -> UserResponse:
    return UserResponse.model_validate(await service.register(session, data))


@router.post(
    "/auth/login",
    response_model=TokenResponse,
    summary="Вход по email и паролю",
    description=(
        "Проверяет учётные данные и выдаёт JWT access-токен (expires_in 1800 с). "
        "Неверный email и неверный пароль дают одинаковый ответ 401, "
        "чтобы не перечислять существующие адреса. "
        "Без настроенного JWT_SECRET возвращает 503."
    ),
    responses={
        400: error_response(BAD_BODY),
        401: error_response("Неверный email или пароль."),
        429: error_response(RATE_LIMIT_HEADER),
        503: error_response("JWT_SECRET не настроен или Redis недоступен."),
    },
)
async def login(data: Credentials, session: Session, settings: AppSettings) -> TokenResponse:
    return await service.login(session, data, settings)


@router.get(
    "/users/me",
    response_model=UserResponse,
    summary="Данные текущего пользователя",
    description="Возвращает пользователя по Bearer-токену: id, email и display_name.",
    responses={
        401: error_response(UNAUTHORIZED),
        429: error_response(RATE_LIMIT),
    },
)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.get(
    "/auth/github/login",
    status_code=302,
    summary="Начало входа через GitHub",
    description=(
        "Редиректит на GitHub с одноразовым state. Ставит cookie cowrite_oauth_browser "
        "(HttpOnly, SameSite=Lax, 300 с), которая привязывает обмен кода к этому браузеру. "
        "Cookie нельзя передать из fetch: переход выполняет браузер."
    ),
    responses={
        429: error_response(RATE_LIMIT_HEADER),
        503: error_response("GitHub OAuth не настроен: не заданы ключи приложения."),
    },
)
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


@router.get(
    "/auth/github/callback",
    status_code=302,
    summary="Обратный вызов GitHub OAuth",
    description=(
        "Проверяет state и cookie, обменивает code на токен GitHub, читает профиль и email, "
        "создаёт или находит пользователя по github_id. При успехе редиректит на фронтенд "
        "с одноразовым кодом для /auth/exchange. Ответы содержат Cache-Control: no-store."
    ),
    responses={
        400: error_response(
            "Некорректный ответ GitHub, неподтверждённый primary email или неверный state."
        ),
        409: error_response("Email уже занят локальным аккаунтом — войдите в него."),
        429: error_response(RATE_LIMIT_HEADER),
        502: error_response("GitHub API недоступен или вернул ошибку."),
    },
)
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


@router.post(
    "/auth/exchange",
    response_model=TokenResponse,
    summary="Обмен одноразового кода на JWT",
    description=(
        "Завершает вход через GitHub: принимает code из редиректа callback, "
        "проверяет привязку к браузеру и пятиминутный срок действия. "
        "Код одноразовый: повторный обмен возвращает 400."
    ),
    responses={
        400: error_response("Код не найден, просрочен, уже использован или не совпадает браузер."),
        401: error_response("Пользователь удалён после прохождения OAuth."),
        429: error_response(RATE_LIMIT_HEADER),
    },
)
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
