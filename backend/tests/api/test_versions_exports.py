import uuid
from unittest.mock import MagicMock

import pytest
from pycrdt import Doc, Text
from pydantic import SecretStr

from app.core.config import Settings
from app.core.security import create_access_token
from app.models import Document, DocumentMember, User
from app.modules.exports.service import cleanup, render_job
from app.modules.versions.service import scheduled

pytestmark = pytest.mark.integration


@pytest.fixture
async def context(db_session):
    users = [
        User(email=f"{name}@example.com", display_name=name, password_hash="hash")
        for name in ("owner", "editor", "viewer", "stranger")
    ]
    db_session.add_all(users)
    await db_session.flush()
    doc = Doc()
    doc.get("text", type=Text).insert(0, "Первая версия")
    document = Document(owner_id=users[0].id, ydoc_state=doc.get_update())
    db_session.add(document)
    await db_session.flush()
    db_session.add_all(
        [
            DocumentMember(document_id=document.id, user_id=user.id, role=role)
            for user, role in zip(users[1:3], ("editor", "viewer"), strict=True)
        ]
    )
    await db_session.flush()
    settings = Settings(
        _env_file=None, jwt_secret=SecretStr("test-only-secret-with-at-least-32-bytes")
    )
    headers = [
        {"Authorization": f"Bearer {create_access_token(user.id, settings)}"} for user in users
    ]
    return document, users, headers


async def test_snapshot_restore_preserves_history(api_client, db_session, context):
    document, _, headers = context
    path = f"/documents/{document.id}"
    version = await api_client.post(path + "/versions", headers=headers[0])
    assert version.status_code == 201
    version_id = version.json()["id"]
    changed = Doc()
    changed.get("text", type=Text).insert(0, "Другая версия")
    document.ydoc_state = changed.get_update()
    document.state_revision += 1
    await db_session.commit()
    restored = await api_client.post(path + f"/versions/{version_id}/restore", headers=headers[1])
    assert restored.status_code == 200
    assert restored.json()["generation"] == 2
    assert restored.json()["state_revision"] == 2
    await db_session.refresh(document)
    result = Doc()
    result.apply_update(document.ydoc_state)
    assert str(result.get("text", type=Text)) == "Первая версия"
    history = (await api_client.get(path + "/versions", headers=headers[2])).json()
    assert len(history) == 2
    assert "state" not in history[0]
    assert any(item["id"] == version_id for item in history)
    assert (await api_client.post(path + "/versions", headers=headers[2])).status_code == 403
    assert (
        await api_client.post(path + f"/versions/{version_id}/restore", headers=headers[2])
    ).status_code == 403
    assert (await api_client.get(path + "/versions", headers=headers[3])).status_code == 403
    assert (
        await api_client.post(path + f"/versions/{uuid.uuid4()}/restore", headers=headers[0])
    ).status_code == 404


async def test_scheduled_snapshots_are_idempotent(db_session, context):
    document, _, _ = context
    assert await scheduled(db_session) == 1
    assert await scheduled(db_session) == 0
    document.state_revision += 1
    await db_session.commit()
    assert await scheduled(db_session) == 1


async def test_export_access_queue_and_failure(
    api_client, db_session, context, monkeypatch, tmp_path
):
    from app.models import ExportJob
    from app.worker import pdf

    document, _, headers = context
    queue = MagicMock()
    monkeypatch.setattr(pdf, "apply_async", queue)
    result = await api_client.post(f"/documents/{document.id}/export", headers=headers[2])
    assert result.status_code == 202
    job_id = result.json()["task_id"]
    assert queue.call_args.kwargs["args"] == [job_id]
    assert queue.call_args.kwargs["task_id"] == job_id
    path = f"/exports/{job_id}"
    assert (await api_client.get(path, headers=headers[2])).json()["status"] == "queued"
    assert (await api_client.get(path, headers=headers[0])).status_code == 403
    assert (await api_client.get(path + "/file", headers=headers[2])).status_code == 409
    settings = Settings(_env_file=None, exports_dir=tmp_path, pdf_fonts_dir=tmp_path / "missing")
    await render_job(db_session, settings, job_id)
    job = await db_session.get(ExportJob, uuid.UUID(job_id))
    assert job.status == "failed"
    assert job.error_code == "pdf_generation_failed"
    queue.side_effect = ConnectionError("offline")
    failed = await api_client.post(f"/documents/{document.id}/export", headers=headers[0])
    assert failed.status_code == 503
    assert (await api_client.get(f"/exports/{uuid.uuid4()}", headers=headers[0])).status_code == 404
    await cleanup(db_session, settings)
