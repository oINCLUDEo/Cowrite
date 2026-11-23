"""Celery использует только JSON; каждый запуск создаёт свой async event loop и пул БД."""

import asyncio
from typing import Any

import structlog
from celery import Celery  # type: ignore[import-untyped]
from celery.signals import task_failure, task_postrun, task_prerun  # type: ignore[import-untyped]

from app.core.config import get_settings
from app.core.db import Database
from app.core.logging import configure_log_redaction

configure_log_redaction()
logger = structlog.get_logger()


@task_prerun.connect  # type: ignore[untyped-decorator]
def task_started(task: Any = None, **kwargs: Any) -> None:
    headers = getattr(task.request, "headers", None) or {}
    structlog.contextvars.bind_contextvars(
        service="worker", task_id=task.request.id, request_id=headers.get("request_id", "")
    )
    logger.info("task_started", task_name=task.name)


@task_postrun.connect  # type: ignore[untyped-decorator]
def task_finished(state: str = "", **kwargs: Any) -> None:
    logger.info("task_finished", state=state)
    structlog.contextvars.clear_contextvars()


@task_failure.connect  # type: ignore[untyped-decorator]
def task_failed(**kwargs: Any) -> None:
    logger.error("task_failed")


settings = get_settings()
celery = Celery(
    "cowrite", broker=settings.celery_broker_url, backend=settings.celery_result_backend
)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_time_limit=120,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    beat_schedule={
        "scheduled-versions": {"task": "cowrite.snapshots", "schedule": 300.0},
        "cleanup-exports": {"task": "cowrite.cleanup", "schedule": 3600.0},
    },
)


@celery.task(name="cowrite.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    return "pong"


async def run_service(name: str, *args: Any) -> Any:
    database = Database(settings)
    try:
        async with database.sessions() as session:
            if name == "snapshots":
                from app.modules.versions.service import scheduled

                return await scheduled(session)
            if name == "pdf":
                from app.modules.exports.service import render_job

                return await render_job(session, settings, *args)
            if name == "invite":
                from app.modules.notifications.service import send_invitation

                return await send_invitation(session, settings, *args)
            from app.modules.exports.service import cleanup

            return await cleanup(session, settings)
    finally:
        await database.close()


@celery.task(name="cowrite.snapshots")  # type: ignore[untyped-decorator]
def snapshots() -> int:
    return int(asyncio.run(run_service("snapshots")))


@celery.task(name="cowrite.pdf")  # type: ignore[untyped-decorator]
def pdf(job_id: str) -> None:
    asyncio.run(run_service("pdf", job_id))


@celery.task(name="cowrite.cleanup")  # type: ignore[untyped-decorator]
def cleanup_exports() -> None:
    asyncio.run(run_service("cleanup"))


@celery.task(bind=True, name="cowrite.invite", max_retries=3)  # type: ignore[untyped-decorator]
def invite(self: Any, document_id: str, user_id: str, inviter_id: str, message_id: str) -> None:
    try:
        asyncio.run(run_service("invite", document_id, user_id, inviter_id, message_id))
    except Exception as error:
        if self.request.retries >= 3:
            raise
        raise self.retry(exc=error, countdown=[10, 30, 90][self.request.retries]) from error
