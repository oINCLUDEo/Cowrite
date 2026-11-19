from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.modules.auth.deps import AppSettings, CurrentUser, Session
from app.modules.documents.deps import Rooms, mutation_lock
from app.modules.exports import service
from app.modules.exports.schemas import ExportAccepted, ExportResponse

router = APIRouter(tags=["exports"])


@router.post("/documents/{document_id}/export", status_code=202, response_model=ExportAccepted)
async def export(
    document_id: UUID, user: CurrentUser, session: Session, rooms: Rooms, request: Request
) -> ExportAccepted:
    from app.worker import pdf

    async with mutation_lock(rooms, document_id):
        job_id = await service.create(session, rooms, document_id, user.id)
    try:
        await run_in_threadpool(pdf.apply_async, args=[str(job_id)], task_id=str(job_id),
                                headers={"request_id": getattr(request.state, "request_id", "")})
    except Exception:
        await service.queue_failed(session, job_id)
        raise HTTPException(
            503, detail={"code": "queue_unavailable", "message": "Очередь недоступна"}
        ) from None
    return ExportAccepted(task_id=job_id)


@router.get("/exports/{job_id}", response_model=ExportResponse)
async def status(job_id: UUID, user: CurrentUser, session: Session) -> ExportResponse:
    return ExportResponse.model_validate(await service.get_job(session, job_id, user.id))


@router.get(
    "/exports/{job_id}/file",
    response_class=FileResponse,
    responses={
        200: {
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
            "description": "PDF attachment",
        }
    },
)
async def file(
    job_id: UUID, user: CurrentUser, session: Session, settings: AppSettings
) -> FileResponse:
    job = await service.get_job(session, job_id, user.id)
    return FileResponse(
        service.file_path(settings, job),
        media_type="application/pdf",
        filename=f"document-{job_id}.pdf",
    )
