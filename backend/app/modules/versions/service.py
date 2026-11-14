"""Неизменяемые снапшоты и восстановление со сменой поколения."""

import uuid
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.collab.rooms import RoomManager
from app.modules.documents.models import Document
from app.modules.documents.schemas import DocumentResponse
from app.modules.documents.service import require_role, response
from app.modules.versions.models import DocumentVersion
from app.modules.versions.schemas import VersionResponse


async def list_versions(
    session: AsyncSession, document_id: uuid.UUID, user_id: uuid.UUID, limit: int, offset: int
) -> list[VersionResponse]:
    await require_role(session, document_id, user_id)
    versions = await session.scalars(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.created_at.desc(), DocumentVersion.id)
        .limit(limit)
        .offset(offset)
    )
    return [VersionResponse.model_validate(version) for version in versions]


def snapshot(
    document: Document,
    user_id: uuid.UUID | None,
    kind: Literal["manual", "scheduled", "export"] = "manual",
) -> DocumentVersion:
    return DocumentVersion(
        document_id=document.id,
        state=document.ydoc_state,
        source_revision=document.state_revision,
        created_by=user_id,
        kind=kind,
    )


async def current_document(
    session: AsyncSession,
    manager: RoomManager | None,
    document_id: uuid.UUID,
    user_id: uuid.UUID,
    minimum: Literal["viewer", "editor"] = "editor",
) -> Document:
    document, _ = await require_role(session, document_id, user_id, minimum, lock=True)
    room = manager.rooms.get(document_id) if manager else None
    if room and room.dirty:
        document.ydoc_state = room.doc.get_update()
        document.state_revision += 1
    return document


async def committed(manager: RoomManager | None, document: Document) -> None:
    room = manager.rooms.get(document.id) if manager else None
    if room:
        room.dirty = False
        room.failed_since = None
        room.revision = document.state_revision
        await room.notify()


async def create(
    session: AsyncSession, manager: RoomManager | None, document_id: uuid.UUID, user_id: uuid.UUID
) -> VersionResponse:
    document = await current_document(session, manager, document_id, user_id)
    version = snapshot(document, user_id)
    session.add(version)
    await session.commit()
    await committed(manager, document)
    return VersionResponse.model_validate(version)


async def restore(
    session: AsyncSession,
    manager: RoomManager | None,
    document_id: uuid.UUID,
    version_id: uuid.UUID,
    user_id: uuid.UUID,
) -> DocumentResponse:
    document = await current_document(session, manager, document_id, user_id)
    version = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.id == version_id, DocumentVersion.document_id == document_id
        )
    )
    if version is None:
        raise HTTPException(
            404, detail={"code": "version_not_found", "message": "Версия не найдена"}
        )
    session.add(snapshot(document, user_id))
    document.ydoc_state = version.state
    document.state_revision += 1
    document.generation += 1
    await session.commit()
    await session.refresh(document)
    if manager and (room := manager.rooms.pop(document_id, None)):
        room.dirty = False
        await manager.close_peers(room, 4409)
    _, role = await require_role(session, document_id, user_id)
    return response(document, role)


async def scheduled(session: AsyncSession) -> int:
    count = 0
    documents = await session.scalars(select(Document).order_by(Document.id).with_for_update())
    for document in documents:
        exists = await session.scalar(
            select(DocumentVersion.id).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.kind == "scheduled",
                DocumentVersion.source_revision == document.state_revision,
            )
        )
        if exists is None:
            session.add(snapshot(document, None, "scheduled"))
            count += 1
    await session.commit()
    return count
