"""REST документов. Проверки доступа и транзакции делегируются сервису."""

from email.utils import make_msgid
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from app.core.schemas import error_response
from app.modules.auth.deps import CurrentUser, Session
from app.modules.documents import service
from app.modules.documents.deps import Rooms, mutation_lock
from app.modules.documents.schemas import (
    CreateDocument,
    DocumentResponse,
    MemberRequest,
    MemberResponse,
    RenameDocument,
)

router = APIRouter(prefix="/documents", tags=["documents"])

UNAUTHORIZED = "Access-токен не передан, истёк или невалиден."
RATE_LIMIT = "Слишком много запросов. Лимит на IP: 120/мин."
NO_ACCESS = "Документ существует, но у пользователя нет прав даже на чтение."
NOT_FOUND = "Документ удалён или идентификатор неверен."

# Ответы, общие для всех маршрутов раздела.
COMMON: dict[int | str, dict[str, Any]] = {
    401: error_response(UNAUTHORIZED),
    403: error_response(NO_ACCESS),
    404: error_response(NOT_FOUND),
    429: error_response(RATE_LIMIT),
}

# Ответы маршрутов, изменяющих состояние: дополнительно 413 на большое тело.
MUTATING: dict[int | str, dict[str, Any]] = {
    **COMMON,
    413: error_response("Тело запроса превышает 1 MiB."),
}

# Маршруты владельца: здесь 403 означает не «нет доступа», а «роль ниже owner».
OWNER_ONLY: dict[int | str, dict[str, Any]] = {
    **COMMON,
    403: error_response("Операция доступна только владельцу документа."),
}


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=201,
    summary="Создать документ",
    description=(
        "Создаёт пустой документ, где вызвавший становится владельцем. "
        "Заголовок после обрезки пробелов должен иметь длину 1–200 символов; "
        "по умолчанию «Без названия». Новый документ содержит пустое состояние Yjs."
    ),
    responses={**MUTATING},
)
async def create_document(
    data: CreateDocument, user: CurrentUser, session: Session
) -> DocumentResponse:
    return await service.create(session, user.id, data.title)


@router.get(
    "",
    response_model=list[DocumentResponse],
    summary="Список документов",
    description=(
        "Возвращает собственные и расшарённые документы, отсортированные по updated_at "
        "по убыванию. Поле role указывает роль вызвавшего: owner, editor или viewer."
    ),
    responses={**COMMON},
)
async def list_documents(
    user: CurrentUser,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=100, description="Размер страницы, 1–100.")] = 20,
    offset: Annotated[int, Query(ge=0, description="Смещение для пагинации.")] = 0,
) -> list[DocumentResponse]:
    return await service.list_documents(session, user.id, limit, offset)


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Метаданные документа",
    description=(
        "Метаданные без байтов CRDT. generation нужен для подключения к WebSocket: "
        "он меняется при откате версии, и клиент обязан перечитать его перед соединением."
    ),
    responses={**COMMON},
)
async def get_document(document_id: UUID, user: CurrentUser, session: Session) -> DocumentResponse:
    document, role = await service.require_role(session, document_id, user.id)
    return service.response(document, role)


@router.patch(
    "/{document_id}",
    response_model=DocumentResponse,
    summary="Переименовать документ",
    description="Меняет только заголовок. Доступно владельцу; редактору — 403.",
    responses={
        **MUTATING,
        403: error_response("Роль ниже owner: переименование доступно только владельцу."),
    },
)
async def rename_document(
    document_id: UUID, data: RenameDocument, user: CurrentUser, session: Session
) -> DocumentResponse:
    return await service.rename(session, document_id, user.id, data.title)


@router.delete(
    "/{document_id}",
    status_code=204,
    summary="Удалить документ",
    description=(
        "Удаляет документ вместе с участниками, версиями и заданиями экспорта. "
        "Подключённые клиенты получают закрытие WebSocket с кодом 4404. "
        "Операция доступна только владельцу."
    ),
    responses={**OWNER_ONLY},
)
async def delete_document(
    document_id: UUID, user: CurrentUser, session: Session, rooms: Rooms
) -> None:
    async with mutation_lock(rooms, document_id):
        await service.delete(session, document_id, user.id)
        if rooms and (room := rooms.rooms.pop(document_id, None)):
            await rooms.close_peers(room, 4404)


@router.get(
    "/{document_id}/members",
    response_model=list[MemberResponse],
    summary="Список участников",
    description=(
        "Участники с email, именем и ролью editor или viewer. Владелец в список не входит: "
        "он хранится в owner_id документа. Список доступен только владельцу."
    ),
    responses={**OWNER_ONLY},
)
async def list_members(
    document_id: UUID, user: CurrentUser, session: Session
) -> list[MemberResponse]:
    return await service.members(session, document_id, user.id)


@router.post(
    "/{document_id}/members",
    response_model=MemberResponse,
    summary="Добавить участника или изменить роль",
    description=(
        "Идемпотентная операция: добавляет пользователя по email или обновляет его роль. "
        "Пользователь с таким email должен быть зарегистрирован. "
        "После успеха ставится задача отправки приглашения по SMTP: "
        "поле notification принимает queued, queue_failed или not_configured. "
        "Смена роли применяется к активным WebSocket-соединениям сразу."
    ),
    responses={
        **OWNER_ONLY,
        413: error_response("Тело запроса превышает 1 MiB."),
        404: error_response(
            "Документ не найден или пользователь с таким email не зарегистрирован."
        ),
        409: error_response("Нельзя изменить или удалить права владельца документа."),
        503: error_response("Redis недоступен — защита запросов не может продолжить работу."),
    },
)
async def put_member(
    document_id: UUID,
    data: MemberRequest,
    user: CurrentUser,
    session: Session,
    rooms: Rooms,
    request: Request,
) -> MemberResponse:
    async with mutation_lock(rooms, document_id):
        member = await service.put_member(session, document_id, user.id, data)
        if rooms:
            await rooms.change_role(document_id, member.user_id, data.role)
    from app.worker import invite

    try:
        await run_in_threadpool(
            invite.apply_async,
            args=[
                str(document_id),
                str(member.user_id),
                str(user.id),
                make_msgid(domain="cowrite.local"),
            ],
            headers={"request_id": getattr(request.state, "request_id", "")},
        )
        member.notification = "queued"
    except Exception:
        member.notification = "queue_failed"
    return member


@router.delete(
    "/{document_id}/members/{member_id}",
    status_code=204,
    summary="Удалить участника",
    description=(
        "Отзывает доступ. Активное соединение пользователя закрывается с кодом 4403, "
        "кэш прав сбрасывается немедленно, без ожидания истечения 60 секунд."
    ),
    responses={
        **COMMON,
        404: error_response("Документ не найден или пользователь не является участником."),
        409: error_response("Нельзя удалить владельца документа."),
    },
)
async def remove_member(
    document_id: UUID, member_id: UUID, user: CurrentUser, session: Session, rooms: Rooms
) -> None:
    async with mutation_lock(rooms, document_id):
        await service.remove_member(session, document_id, user.id, member_id)
        if rooms:
            await rooms.change_role(document_id, member_id, None)
