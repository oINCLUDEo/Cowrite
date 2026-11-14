"""REST документов. Проверки доступа и транзакции делегируются сервису."""

from email.utils import make_msgid
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

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


@router.post("", response_model=DocumentResponse, status_code=201)
async def create_document(
    data: CreateDocument, user: CurrentUser, session: Session
) -> DocumentResponse:
    return await service.create(session, user.id, data.title)


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    user: CurrentUser,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DocumentResponse]:
    return await service.list_documents(session, user.id, limit, offset)


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: UUID, user: CurrentUser, session: Session) -> DocumentResponse:
    document, role = await service.require_role(session, document_id, user.id)
    return service.response(document, role)


@router.patch("/{document_id}", response_model=DocumentResponse)
async def rename_document(
    document_id: UUID, data: RenameDocument, user: CurrentUser, session: Session
) -> DocumentResponse:
    return await service.rename(session, document_id, user.id, data.title)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: UUID, user: CurrentUser, session: Session, rooms: Rooms
) -> None:
    async with mutation_lock(rooms, document_id):
        await service.delete(session, document_id, user.id)
        if rooms and (room := rooms.rooms.pop(document_id, None)):
            await rooms.close_peers(room, 4404)


@router.get("/{document_id}/members", response_model=list[MemberResponse])
async def list_members(
    document_id: UUID, user: CurrentUser, session: Session
) -> list[MemberResponse]:
    return await service.members(session, document_id, user.id)


@router.post("/{document_id}/members", response_model=MemberResponse)
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


@router.delete("/{document_id}/members/{member_id}", status_code=204)
async def remove_member(
    document_id: UUID, member_id: UUID, user: CurrentUser, session: Session, rooms: Rooms
) -> None:
    async with mutation_lock(rooms, document_id):
        await service.remove_member(session, document_id, user.id, member_id)
        if rooms:
            await rooms.change_role(document_id, member_id, None)
