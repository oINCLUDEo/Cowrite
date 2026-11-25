"""REST истории версий: список, ручной снапшот и откат."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.schemas import error_response
from app.modules.auth.deps import CurrentUser, Session
from app.modules.documents.deps import Rooms, mutation_lock
from app.modules.documents.schemas import DocumentResponse
from app.modules.versions import service
from app.modules.versions.schemas import VersionResponse

router = APIRouter(tags=["versions"])

UNAUTHORIZED = "Access-токен не передан, истёк или невалиден."
RATE_LIMIT = "Слишком много запросов. Лимит на IP: 120/мин."
NOT_FOUND = "Документ удалён или идентификатор неверен."
VIEWER_ONLY = "Роль viewer: прав на изменение нет, только чтение."
COMMON: dict[int | str, dict[str, Any]] = {
    401: error_response(UNAUTHORIZED),
    403: error_response("Документ существует, но у пользователя нет прав даже на чтение."),
    404: error_response(NOT_FOUND),
    429: error_response(RATE_LIMIT),
}


@router.get(
    "/documents/{document_id}/versions",
    response_model=list[VersionResponse],
    summary="Список версий",
    description=(
        "Снапшоты документа от новых к старым. kind: manual (создан вручную), "
        "scheduled (периодический снапшот beat каждые 5 минут) или export "
        "(снимок, закреплённый заданием экспорта). "
        "Байты CRDT в ответ не входят — только метаданные."
    ),
    responses={**COMMON},
)
async def list_versions(
    document_id: UUID,
    user: CurrentUser,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=100, description="Размер страницы, 1–100.")] = 20,
    offset: Annotated[int, Query(ge=0, description="Смещение для пагинации.")] = 0,
) -> list[VersionResponse]:
    return await service.list_versions(session, document_id, user.id, limit, offset)


@router.post(
    "/documents/{document_id}/versions",
    response_model=VersionResponse,
    status_code=201,
    summary="Создать снапшот вручную",
    description=(
        "Сохраняет текущее состояние документа как версию kind=manual. "
        "Если в комнате есть несохранённые правки, они сначала фиксируются "
        "в документе и увеличивают state_revision. Доступен owner и editor."
    ),
    responses={**COMMON, 403: error_response(VIEWER_ONLY)},
)
async def create(
    document_id: UUID, user: CurrentUser, session: Session, rooms: Rooms
) -> VersionResponse:
    async with mutation_lock(rooms, document_id):
        return await service.create(session, rooms, document_id, user.id)


@router.post(
    "/documents/{document_id}/versions/{version_id}/restore",
    response_model=DocumentResponse,
    summary="Откатить документ к версии",
    description=(
        "Перед откатом создаёт резервную версию текущего состояния, затем "
        "заменяет состояние документа выбранным снапшотом. Увеличиваются "
        "state_revision и generation: подключённые клиенты получают закрытие "
        "WebSocket с кодом 4409 и переподключаются с новым поколением, поэтому "
        "их несохранённые правки старого поколения не смешиваются с откатом. "
        "Ответ содержит новый generation для переподключения. Доступен owner и editor."
    ),
    responses={
        **COMMON,
        403: error_response(VIEWER_ONLY),
        404: error_response("Документ не найден или версия принадлежит другому документу."),
    },
)
async def restore(
    document_id: UUID, version_id: UUID, user: CurrentUser, session: Session, rooms: Rooms
) -> DocumentResponse:
    async with mutation_lock(rooms, document_id):
        return await service.restore(session, rooms, document_id, version_id, user.id)
