"""Документы и права: все SQL-запросы и изменения выполняются здесь."""

import uuid
from contextlib import nullcontext

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.documents.models import Document, DocumentMember
from app.modules.documents.schemas import DocumentResponse, MemberRequest, MemberResponse, Role


async def require_role(
    session: AsyncSession,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    minimum: Role = "viewer",
    *,
    lock: bool = False,
) -> tuple[Document, Role]:
    query = select(Document).where(Document.id == document_id)
    if lock:
        query = query.with_for_update()
    document = await session.scalar(query)
    if document is None:
        raise HTTPException(
            404, detail={"code": "document_not_found", "message": "Документ не найден"}
        )
    cache = session.info.get("role_cache")
    async with cache.lock(user_id, document_id) if cache else nullcontext():
        cached = await cache.get(user_id, document_id) if cache else None
        role: Role | None = (
            "owner"
            if document.owner_id == user_id
            else cached
            if cached in ("editor", "viewer")
            else None
            if cached == "none"
            else await session.scalar(
                select(DocumentMember.role).where(
                    DocumentMember.document_id == document_id,
                    DocumentMember.user_id == user_id,
                )
            )
        )
        if cache and cached is None:
            await cache.put(user_id, document_id, role or "none")
    ranks = {"viewer": 0, "editor": 1, "owner": 2}
    if role is None or ranks[role] < ranks[minimum]:
        raise HTTPException(403, detail={"code": "access_denied", "message": "Недостаточно прав"})
    return document, role


def response(document: Document, role: Role) -> DocumentResponse:
    return DocumentResponse.model_validate(
        {
            **{
                name: getattr(document, name)
                for name in DocumentResponse.model_fields
                if name != "role"
            },
            "role": role,
        }
    )


async def create(session: AsyncSession, user_id: uuid.UUID, title: str) -> DocumentResponse:
    document = Document(owner_id=user_id, title=title)
    session.add(document)
    await session.commit()
    return response(document, "owner")


async def list_documents(
    session: AsyncSession,
    user_id: uuid.UUID,
    limit: int,
    offset: int,
) -> list[DocumentResponse]:
    rows = await session.execute(
        select(Document, DocumentMember.role)
        .outerjoin(
            DocumentMember,
            (DocumentMember.document_id == Document.id) & (DocumentMember.user_id == user_id),
        )
        .where(or_(Document.owner_id == user_id, DocumentMember.user_id == user_id))
        .order_by(Document.updated_at.desc(), Document.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        response(document, "owner" if document.owner_id == user_id else role)
        for document, role in rows
    ]


async def rename(
    session: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID, title: str
) -> DocumentResponse:
    document, role = await require_role(session, document_id, user_id, "owner", lock=True)
    document.title = title
    await session.commit()
    # updated_at вычисляет PostgreSQL; загружаем его явно, без неявного async IO.
    await session.refresh(document)
    return response(document, role)


async def delete(session: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID) -> None:
    document, _ = await require_role(session, document_id, user_id, "owner", lock=True)
    await session.delete(document)
    await session.commit()


async def members(
    session: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID
) -> list[MemberResponse]:
    await require_role(session, document_id, user_id, "owner")
    rows = await session.execute(
        select(User, DocumentMember.role)
        .join(DocumentMember, DocumentMember.user_id == User.id)
        .where(DocumentMember.document_id == document_id)
        .order_by(User.email)
    )
    return [
        MemberResponse(user_id=user.id, email=user.email, display_name=user.display_name, role=role)
        for user, role in rows
    ]


async def put_member(
    session: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID, data: MemberRequest
) -> MemberResponse:
    document, _ = await require_role(session, document_id, user_id, "owner", lock=True)
    user = await session.scalar(select(User).where(User.email == str(data.email)))
    if user is None:
        raise HTTPException(
            404, detail={"code": "user_not_found", "message": "Пользователь не зарегистрирован"}
        )
    if user.id == document.owner_id:
        raise HTTPException(
            409, detail={"code": "owner_membership", "message": "Права владельца нельзя изменить"}
        )
    await session.execute(
        insert(DocumentMember)
        .values(document_id=document_id, user_id=user.id, role=data.role)
        .on_conflict_do_update(
            index_elements=[DocumentMember.document_id, DocumentMember.user_id],
            set_={"role": data.role},
        )
    )
    await session.commit()
    if cache := session.info.get("role_cache"):
        await cache.invalidate(user.id, document_id)
    return MemberResponse(
        user_id=user.id, email=user.email, display_name=user.display_name, role=data.role
    )


async def remove_member(
    session: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID, member_id: uuid.UUID
) -> None:
    document, _ = await require_role(session, document_id, user_id, "owner", lock=True)
    if member_id == document.owner_id:
        raise HTTPException(
            409, detail={"code": "owner_membership", "message": "Нельзя удалить владельца"}
        )
    member = await session.get(DocumentMember, (document_id, member_id))
    if member is None:
        raise HTTPException(
            404, detail={"code": "member_not_found", "message": "Участник не найден"}
        )
    await session.delete(member)
    await session.commit()
    if cache := session.info.get("role_cache"):
        await cache.invalidate(member_id, document_id)
