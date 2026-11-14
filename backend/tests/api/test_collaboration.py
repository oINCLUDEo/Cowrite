import asyncio
import uuid

import anyio
import pytest
from fastapi.testclient import TestClient
from pycrdt import Doc, Text, create_sync_message, create_update_message, handle_sync_message
from pydantic import SecretStr
from sqlalchemy import delete

from app.core.config import Settings
from app.core.db import Database
from app.core.security import create_access_token
from app.main import create_app
from app.models import Document, DocumentMember, User

pytestmark = pytest.mark.integration


@pytest.fixture
def secured(test_database_url):
    settings = Settings(
        _env_file=None,
        database_url=test_database_url,
        jwt_secret=SecretStr("test-only-secret-with-at-least-32-bytes"),
        allowed_origins=["http://testserver"],
    )

    async def setup():
        database = Database(settings)
        async with database.sessions() as session:
            users = [
                User(email=f"{uuid.uuid4()}@example.com", display_name=name, password_hash="hash")
                for name in ("owner", "editor", "viewer", "stranger")
            ]
            session.add_all(users)
            await session.flush()
            document = Document(owner_id=users[0].id)
            session.add(document)
            await session.flush()
            session.add_all(
                [
                    DocumentMember(document_id=document.id, user_id=users[1].id, role="editor"),
                    DocumentMember(document_id=document.id, user_id=users[2].id, role="viewer"),
                ]
            )
            await session.commit()
        await database.close()
        return users, document

    users, document = asyncio.run(setup())
    app = create_app(settings)
    with TestClient(app) as client:
        yield app, client, document, users, settings

    async def cleanup():
        database = Database(settings)
        async with database.sessions() as session:
            await session.execute(
                delete(Document).where(Document.owner_id.in_([u.id for u in users]))
            )
            await session.execute(delete(User).where(User.id.in_([u.id for u in users])))
            await session.commit()
        await database.close()

    asyncio.run(cleanup())


def connect(client, document, user, settings, generation=1):
    token = create_access_token(user.id, settings)
    return client.websocket_connect(
        f"/ws/documents/{document.id}?token={token}&generation={generation}",
        headers={"Origin": "http://testserver"},
    )


def synchronize(websocket, doc):
    message = websocket.receive_bytes()
    reply = handle_sync_message(message[1:], doc)
    if reply is not None:
        websocket.send_bytes(reply)
    websocket.send_bytes(create_sync_message(doc))
    message = websocket.receive_bytes()
    handle_sync_message(message[1:], doc)


def receive_until_text(websocket, doc, expected):
    for _ in range(10):

        async def receive_with_timeout():
            with anyio.fail_after(3):
                return await websocket._send_rx.receive()

        frame = websocket.portal.call(receive_with_timeout)
        assert frame["type"] == "websocket.send", frame
        message = frame["bytes"]
        if message[0] == 0:
            reply = handle_sync_message(message[1:], doc)
            if reply is not None:
                websocket.send_bytes(reply)
        if str(doc.get("text", type=Text)) == expected:
            return
    raise AssertionError(f"Did not receive expected text: {expected}")


def test_two_clients_receive_each_others_changes(secured):
    app, client, document, users, settings = secured
    first, second = Doc(), Doc()
    with (
        connect(client, document, users[0], settings) as ws1,
        connect(client, document, users[1], settings) as ws2,
    ):
        synchronize(ws1, first)
        synchronize(ws2, second)
        first.get("text", type=Text).insert(0, "Привет")
        ws1.send_bytes(create_update_message(first.get_update()))
        receive_until_text(ws2, second, "Привет")
        # pycrdt offsets count UTF-8 bytes, not Python Unicode code points.
        text = second.get("text", type=Text)
        text.insert(len(text), ", Cowrite!")
        ws2.send_bytes(create_update_message(second.get_update()))
        receive_until_text(ws1, first, "Привет, Cowrite!")


def test_last_disconnect_saves_and_reloads(secured):
    app, client, document, users, settings = secured
    first = Doc()
    with connect(client, document, users[0], settings) as ws:
        synchronize(ws, first)
        first.get("text", type=Text).insert(0, "Сохранено")
        ws.send_bytes(create_update_message(first.get_update()))
        receive_until_text(ws, first, "Сохранено")

    async def persisted():
        for _ in range(100):
            async with app.state.database.sessions() as session:
                stored = await session.get(Document, document.id)
                doc = Doc()
                doc.apply_update(stored.ydoc_state)
                if str(doc.get("text", type=Text)) == "Сохранено":
                    return True
            await anyio.sleep(0.05)
        return False

    assert client.portal.call(persisted)
    with connect(client, document, users[0], settings) as ws:
        other = Doc()
        synchronize(ws, other)
        assert str(other.get("text", type=Text)) == "Сохранено"


def test_text_frames_are_rejected(secured):
    _, client, document, users, settings = secured
    with connect(client, document, users[0], settings) as websocket:
        websocket.receive_bytes()
        websocket.send_text("not a binary protocol")
        assert websocket.receive()["code"] == 1003


@pytest.mark.parametrize(
    "mode,code", [("stranger", 4403), ("generation", 4409), ("token", 4401), ("origin", 4403)]
)
def test_connection_rejections(secured, mode, code):
    _, client, document, users, settings = secured
    token = create_access_token(users[3 if mode == "stranger" else 0].id, settings)
    token = "bad" if mode == "token" else token
    generation = 2 if mode == "generation" else 1
    path = f"/ws/documents/{document.id}?token={token}&generation={generation}"
    with client.websocket_connect(
        path, headers={"Origin": "http://evil" if mode == "origin" else "http://testserver"}
    ) as ws:
        assert ws.receive()["code"] == code


def test_viewer_cannot_inject_initial_sync_or_updates(secured):
    _, client, document, users, settings = secured
    malicious = Doc()
    malicious.get("text", type=Text).insert(0, "Injected")
    with connect(client, document, users[2], settings) as viewer:
        synchronize(viewer, malicious)
        viewer.send_bytes(create_update_message(malicious.get_update()))
        with connect(client, document, users[0], settings) as owner:
            clean = Doc()
            synchronize(owner, clean)
            assert str(clean.get("text", type=Text)) == ""


def test_active_demotion_and_removal(secured):
    _, client, document, users, settings = secured
    token = create_access_token(users[0].id, settings)
    headers = {"Authorization": f"Bearer {token}"}
    with connect(client, document, users[1], settings) as ws:
        doc = Doc()
        synchronize(ws, doc)
        response = client.post(
            f"/documents/{document.id}/members",
            json={"email": users[1].email, "role": "viewer"},
            headers=headers,
        )
        assert response.status_code == 200
        doc.get("text", type=Text).insert(0, "Forbidden")
        ws.send_bytes(create_update_message(doc.get_update()))
        with connect(client, document, users[0], settings) as owner:
            clean = Doc()
            synchronize(owner, clean)
            assert str(clean.get("text", type=Text)) == ""
        assert (
            client.delete(
                f"/documents/{document.id}/members/{users[1].id}", headers=headers
            ).status_code
            == 204
        )
        assert ws.receive()["code"] == 4403


def test_status_channel_restore_and_old_generation_rejection(secured):
    app, client, document, users, settings = secured
    token = create_access_token(users[0].id, settings)
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/documents/{document.id}"
    with connect(client, document, users[0], settings) as ws:
        doc = Doc()
        synchronize(ws, doc)
        status_path = f"/ws/documents/{document.id}/status?token={token}&generation=1"
        with client.websocket_connect(
            status_path, headers={"Origin": "http://testserver"}
        ) as control:
            assert control.receive_json()["status"] == "saved"
            doc.get("text", type=Text).insert(0, "Снапшот")
            ws.send_bytes(create_update_message(doc.get_update()))
            receive_until_text(ws, doc, "Снапшот")
            assert control.receive_json()["status"] == "unsaved"
            version = client.post(path + "/versions", headers=headers)
            assert version.status_code == 201
            assert control.receive_json()["status"] == "saved"
            doc.get("text", type=Text).insert(0, "Новое ")
            ws.send_bytes(create_update_message(doc.get_update()))
            receive_until_text(ws, doc, "Новое Снапшот")
            assert control.receive_json()["status"] == "unsaved"
            restored = client.post(
                path + f"/versions/{version.json()['id']}/restore", headers=headers
            )
            assert restored.status_code == 200
            assert ws.receive()["code"] == 4409
            assert control.receive()["code"] == 4409
    with connect(client, document, users[0], settings) as stale:
        assert stale.receive()["code"] == 4409
    with connect(client, document, users[0], settings, generation=2) as new:
        clean = Doc()
        synchronize(new, clean)
        assert str(clean.get("text", type=Text)) == "Снапшот"
    assert app.state.rooms.rooms[document.id].generation == 2


def test_connection_limit_and_oversized_message(secured):
    from contextlib import ExitStack

    _, client, document, users, settings = secured
    with ExitStack() as stack:
        for _ in range(10):
            ws = stack.enter_context(connect(client, document, users[0], settings))
            synchronize(ws, Doc())
        with connect(client, document, users[0], settings) as extra:
            assert extra.receive()["code"] == 4429
        ws.send_bytes(b"x" * (1024 * 1024 + 1))
        assert ws.receive()["code"] == 1009
