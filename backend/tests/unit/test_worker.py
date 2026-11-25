from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import structlog

from app import worker


def test_task_context_and_json_configuration(monkeypatch):
    logger = Mock()
    monkeypatch.setattr(worker, "logger", logger)
    task = SimpleNamespace(
        request=SimpleNamespace(id="task-id", headers={"request_id": "request-id"}),
        name="cowrite.pdf",
    )
    worker.task_started(task)
    assert structlog.contextvars.get_contextvars() == {
        "service": "worker",
        "task_id": "task-id",
        "request_id": "request-id",
    }
    worker.task_failed()
    logger.error.assert_called_once_with("task_failed")
    worker.task_finished("SUCCESS")
    assert structlog.contextvars.get_contextvars() == {}
    assert worker.celery.conf.accept_content == ["json"]
    assert worker.celery.conf.task_acks_late
    assert worker.celery.conf.task_reject_on_worker_lost
    assert worker.celery.conf.task_time_limit == 120
    assert worker.ping.run() == "pong"


@pytest.mark.parametrize(
    "name,task,args,result",
    [
        ("snapshots", worker.snapshots, [], 2),
        ("pdf", worker.pdf, ["job-id"], None),
        ("cleanup", worker.cleanup_exports, [], None),
    ],
)
def test_task_calls_async_service(monkeypatch, name, task, args, result):
    service = AsyncMock(return_value=result)
    monkeypatch.setattr(worker, "run_service", service)
    assert task.run(*args) == result
    service.assert_awaited_once_with(name, *args)


@pytest.mark.parametrize("attempt,delay", [(0, 10), (1, 30), (2, 90)])
def test_invitation_retry_schedule(monkeypatch, attempt, delay):
    monkeypatch.setattr(worker, "run_service", AsyncMock(side_effect=OSError("smtp offline")))
    retry = Mock(side_effect=RuntimeError("retry"))
    monkeypatch.setattr(worker.invite, "retry", retry)
    worker.invite.push_request(retries=attempt)
    try:
        with pytest.raises(RuntimeError, match="retry"):
            worker.invite.run("doc", "user", "inviter", "message-id")
        assert retry.call_args.kwargs["countdown"] == delay
    finally:
        worker.invite.pop_request()
