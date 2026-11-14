from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.modules.auth.deps import CurrentUser, Session
from app.modules.documents.deps import Rooms, mutation_lock
from app.modules.documents.schemas import DocumentResponse
from app.modules.versions import service
from app.modules.versions.schemas import VersionResponse

router = APIRouter(tags=["versions"])


@router.get("/documents/{document_id}/versions", response_model=list[VersionResponse])
async def list_versions(
    document_id: UUID,
    user: CurrentUser,
    session: Session,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[VersionResponse]:
    return await service.list_versions(session, document_id, user.id, limit, offset)


@router.post("/documents/{document_id}/versions", response_model=VersionResponse, status_code=201)
async def create(
    document_id: UUID, user: CurrentUser, session: Session, rooms: Rooms
) -> VersionResponse:
    async with mutation_lock(rooms, document_id):
        return await service.create(session, rooms, document_id, user.id)


@router.post(
    "/documents/{document_id}/versions/{version_id}/restore", response_model=DocumentResponse
)
async def restore(
    document_id: UUID, version_id: UUID, user: CurrentUser, session: Session, rooms: Rooms
) -> DocumentResponse:
    async with mutation_lock(rooms, document_id):
        return await service.restore(session, rooms, document_id, version_id, user.id)
