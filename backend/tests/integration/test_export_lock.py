"""Две независимые сессии проверяют видимый running и повторную доставку."""

import asyncio
import threading
import uuid

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.models import Document, DocumentVersion, ExportJob, User
from app.modules.exports import service

pytestmark = pytest.mark.integration


async def test_export_running_is_visible_and_duplicate_waits(
    test_database_url, monkeypatch, tmp_path
):
    engine = create_async_engine(test_database_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    user_id = uuid.uuid4()
    entered, release = threading.Event(), threading.Event()
    calls = []

    def render(state, title, destination, fonts):
        calls.append(title)
        entered.set()
        assert release.wait(10), "Renderer was not released"
        destination.write_bytes(b"%PDF-1.4\nlocked export")

    monkeypatch.setattr(service, "render_pdf", render)
    tasks = []
    try:
        async with sessions() as session:
            user = User(
                id=user_id,
                email=f"{user_id}@example.com",
                display_name="Owner",
                password_hash="hash",
            )
            session.add(user)
            await session.flush()
            document = Document(owner_id=user_id, title="Закреплённая версия")
            session.add(document)
            await session.flush()
            version = DocumentVersion(
                document_id=document.id,
                state=document.ydoc_state,
                source_revision=0,
                kind="export",
                created_by=user_id,
            )
            session.add(version)
            await session.flush()
            job = ExportJob(document_id=document.id, requested_by=user_id, version_id=version.id)
            session.add(job)
            await session.commit()
            job_id = job.id
        settings = Settings(_env_file=None, exports_dir=tmp_path)

        async def run():
            async with sessions() as session:
                await service.render_job(session, settings, str(job_id))

        tasks.append(asyncio.create_task(run()))
        assert await asyncio.to_thread(entered.wait, 5)
        async with sessions() as observer:
            running = await observer.get(ExportJob, job_id)
            assert running.status == "running"
        tasks.append(asyncio.create_task(run()))
        await asyncio.sleep(0.1)
        assert not tasks[1].done()
        assert len(calls) == 1
        release.set()
        await asyncio.gather(*tasks)
        async with sessions() as observer:
            finished = await observer.get(ExportJob, job_id)
            assert finished.status == "succeeded"
            assert finished.finished_at is not None
            assert service.file_path(settings, finished).read_bytes().startswith(b"%PDF-")
        assert len(calls) == 1
        assert not (tmp_path / f"{job_id}.tmp").exists()
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        async with sessions() as session:
            await session.execute(delete(Document).where(Document.owner_id == user_id))
            await session.execute(delete(User).where(User.id == user_id))
            await session.commit()
        await engine.dispose()
