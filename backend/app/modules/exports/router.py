"""REST экспорта: приём задания, статус и скачивание PDF."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.core.schemas import error_response
from app.modules.auth.deps import AppSettings, CurrentUser, Session
from app.modules.documents.deps import Rooms, mutation_lock
from app.modules.exports import service
from app.modules.exports.schemas import ExportAccepted, ExportResponse

router = APIRouter(tags=["exports"])

UNAUTHORIZED = "Access-токен не передан, истёк или невалиден."
RATE_LIMIT = "Слишком много запросов. Лимит на IP: 120/мин."
NOT_FOUND = "Задание или документ не найдены."
COMMON: dict[int | str, dict[str, Any]] = {
    401: error_response(UNAUTHORIZED),
    404: error_response(NOT_FOUND),
    429: error_response(RATE_LIMIT),
}


@router.post(
    "/documents/{document_id}/export",
    status_code=202,
    response_model=ExportAccepted,
    summary="Поставить документ в очередь на экспорт",
    description=(
        "Фиксирует снапшот состояния (kind=export) и ставит задачу в очередь Celery. "
        "Возвращает task_id сразу, не дожидаясь готовности PDF. "
        "Достаточно прав viewer: экспорт не меняет документ. "
        "Готовность проверяется через GET /exports/{task_id}."
    ),
    responses={
        **COMMON,
        403: error_response("Документ не расшарён с вызвавшим."),
        503: error_response(
            "Очередь Celery недоступна: задание помечено failed с error_code queue_unavailable."
        ),
    },
)
async def export(
    document_id: UUID, user: CurrentUser, session: Session, rooms: Rooms, request: Request
) -> ExportAccepted:
    from app.worker import pdf

    async with mutation_lock(rooms, document_id):
        job_id = await service.create(session, rooms, document_id, user.id)
    try:
        await run_in_threadpool(
            pdf.apply_async,
            args=[str(job_id)],
            task_id=str(job_id),
            headers={"request_id": getattr(request.state, "request_id", "")},
        )
    except Exception:
        await service.queue_failed(session, job_id)
        raise HTTPException(
            503, detail={"code": "queue_unavailable", "message": "Очередь недоступна"}
        ) from None
    return ExportAccepted(task_id=job_id)


@router.get(
    "/exports/{job_id}",
    response_model=ExportResponse,
    summary="Статус задания экспорта",
    description=(
        "status проходит путь queued → running → succeeded или failed. "
        "При неудаче error_code содержит pdf_generation_failed или queue_unavailable. "
        "Задание видно только тому, кто его создал, и только пока документ ему доступен."
    ),
    responses={
        **COMMON,
        403: error_response("Задание создал другой пользователь или доступ к документу отозван."),
    },
)
async def status(job_id: UUID, user: CurrentUser, session: Session) -> ExportResponse:
    return ExportResponse.model_validate(await service.get_job(session, job_id, user.id))


@router.get(
    "/exports/{job_id}/file",
    response_class=FileResponse,
    summary="Скачать готовый PDF",
    description=(
        "Отдаёт файл как attachment с именем document-{job_id}.pdf. "
        "Файлы хранятся 24 часа, затем удаляются периодической очисткой. "
        "Опрос документа не меняет: версия закреплена в момент создания задания."
    ),
    responses={
        **COMMON,
        200: {
            "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
            "description": "PDF-файл документа",
        },
        403: error_response("Задание создал другой пользователь."),
        404: error_response("Задание не найдено или срок хранения файла (24 часа) истёк."),
        409: error_response("Задание ещё не завершилось успешно: status не равен succeeded."),
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
