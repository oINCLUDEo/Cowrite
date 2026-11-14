"""Закрепление снапшота, обработка PDF-задания и контроль скачивания."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core.config import Settings
from app.modules.collab.rooms import RoomManager
from app.modules.documents.models import Document
from app.modules.documents.service import require_role
from app.modules.exports.models import ExportJob
from app.modules.exports.pdf import render_pdf
from app.modules.versions.models import DocumentVersion
from app.modules.versions.service import committed, current_document, snapshot

logger = logging.getLogger(__name__)


async def create(
    session: AsyncSession, manager: RoomManager | None, document_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID:
    document = await current_document(session, manager, document_id, user_id, "viewer")
    version = snapshot(document, user_id, "export")
    session.add(version)
    await session.flush()
    job = ExportJob(document_id=document_id, requested_by=user_id, version_id=version.id)
    session.add(job)
    await session.commit()
    await committed(manager, document)
    return job.id


async def get_job(session: AsyncSession, job_id: uuid.UUID, user_id: uuid.UUID) -> ExportJob:
    job = await session.get(ExportJob, job_id)
    if job is None:
        raise HTTPException(
            404, detail={"code": "export_not_found", "message": "Экспорт не найден"}
        )
    if job.requested_by != user_id:
        raise HTTPException(403, detail={"code": "access_denied", "message": "Чужое задание"})
    await require_role(session, job.document_id, user_id)
    return job


def file_path(settings: Settings, job: ExportJob) -> Path:
    path = settings.exports_dir / f"{job.id}.pdf"
    if job.status != "succeeded":
        raise HTTPException(
            409, detail={"code": "export_not_ready", "message": "Файл ещё не готов"}
        )
    if job.created_at < datetime.now(UTC) - timedelta(hours=24) or not path.is_file():
        raise HTTPException(
            404, detail={"code": "export_expired", "message": "Срок хранения файла истёк"}
        )
    return path


async def render_job(session: AsyncSession, settings: Settings, job_id: str) -> None:
    # Session-level advisory lock переживает commit статуса running. Соединение
    # закреплено до конца задачи; повторная доставка ждёт, авария снимает lock.
    bind = session.bind
    if bind is None:
        raise RuntimeError("Export session has no database bind")
    engine = bind.engine if isinstance(bind, AsyncConnection) else bind
    async with engine.connect() as connection:
        key = uuid.UUID(job_id).int % (2**63)
        await connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": key})
        await connection.commit()
        try:
            await _render_locked(session, settings, job_id)
        finally:
            await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            await connection.commit()


async def _render_locked(session: AsyncSession, settings: Settings, job_id: str) -> None:
    job = await session.scalar(
        select(ExportJob).where(ExportJob.id == uuid.UUID(job_id)).with_for_update()
    )
    if job is None or job.status in ("succeeded", "failed"):
        return
    job.status = "running"
    await session.commit()
    version = await session.get(DocumentVersion, job.version_id)
    document = await session.get(Document, job.document_id)
    temporary = settings.exports_dir / f"{job.id}.tmp"
    try:
        if version is None or document is None:
            raise ValueError("Missing snapshot")
        settings.exports_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            render_pdf, version.state, document.title, temporary, settings.pdf_fonts_dir
        )
        temporary.replace(settings.exports_dir / f"{job.id}.pdf")
        job.relative_path = f"{job.id}.pdf"
        job.status = "succeeded"
    except Exception:
        temporary.unlink(missing_ok=True)
        job.status = "failed"
        job.error_code = "pdf_generation_failed"
        logger.warning("PDF generation failed", extra={"task_id": str(job.id)})
    job.finished_at = datetime.now(UTC)
    await session.commit()


async def queue_failed(session: AsyncSession, job_id: uuid.UUID) -> None:
    job = await session.get(ExportJob, job_id)
    if job:
        job.status = "failed"
        job.error_code = "queue_unavailable"
        await session.commit()


async def cleanup(session: AsyncSession, settings: Settings) -> None:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    jobs = await session.scalars(select(ExportJob).where(ExportJob.created_at < cutoff))
    for job in jobs:
        await session.delete(job)
    await session.commit()
    live = set(await session.scalars(select(ExportJob.id)))
    for path in settings.exports_dir.glob("*"):
        try:
            job_id = uuid.UUID(path.stem)
        except ValueError:
            continue
        if job_id not in live:
            path.unlink(missing_ok=True)
