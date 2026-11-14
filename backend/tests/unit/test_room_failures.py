import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pycrdt import Doc, Text, create_update_message

from app.core.config import Settings
from app.models import Document
from app.modules.collab.rooms import Peer, Room, RoomManager


@pytest.fixture
def context():
    session = MagicMock()
    session.scalar = AsyncMock()
    session.commit = AsyncMock()
    database = MagicMock()
    database.sessions.return_value.__aenter__ = AsyncMock(return_value=session)
    database.sessions.return_value.__aexit__ = AsyncMock(return_value=False)
    manager = RoomManager(database, Settings(_env_file=None))
    document = Document(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        generation=1,
        state_revision=0,
        ydoc_state=Doc().get_update(),
    )
    room = Room(document)
    manager.rooms[room.id] = room
    peer = Peer(AsyncMock(), document.owner_id, "token", "editor")
    room.peers.add(peer)
    session.scalar.return_value = document
    return manager, room, peer, session, document


async def test_save_commit_and_failure_recovery(context):
    manager, room, peer, session, document = context
    status = Peer(AsyncMock(), peer.user_id, "token", "editor", status=True)
    room.peers.add(status)
    room.doc.get("text", type=Text).insert(0, "Изменения")
    room.dirty = True
    session.commit.side_effect = ConnectionError()
    assert not await manager.save(room)
    assert room.dirty and room.failed_since
    assert status.websocket.send_json.call_args.args[0]["status"] == "error"
    session.commit.side_effect = None
    assert await manager.save(room)
    assert not room.dirty and room.failed_since is None
    assert status.websocket.send_json.call_args.args[0]["status"] == "saved"
    assert document.ydoc_state == room.doc.get_update()
    assert await manager.save(room)


@pytest.mark.parametrize("deleted,code", [(True, 4404), (False, 4409)])
async def test_save_cannot_overwrite_deleted_or_restored_document(context, deleted, code):
    manager, room, peer, session, document = context
    room.dirty = True
    document.generation = 2
    session.scalar.return_value = None if deleted else document
    assert not await manager.save(room)
    peer.websocket.close.assert_awaited_once_with(code)
    session.commit.assert_not_awaited()


@pytest.mark.parametrize("payload", [b"", b"\x00", b"\x00\x05", b"\x07"])
async def test_invalid_protocol_closes_peer(context, payload):
    manager, room, peer, _, _ = context
    await manager.process(room, peer, payload)
    peer.websocket.close.assert_awaited_once_with(1003)


async def test_revoked_peer_cannot_apply_queued_update(context):
    manager, room, peer, _, _ = context
    doc = Doc()
    doc.get("text", type=Text).insert(0, "Запрещено")
    await manager.change_role(room.id, peer.user_id, None)
    await manager.process(room, peer, create_update_message(doc.get_update()))
    assert not room.dirty
    assert not peer.active


async def test_demote_control_notification_and_database_backpressure(context):
    manager, room, peer, _, _ = context
    peer.status = True
    await manager.change_role(room.id, peer.user_id, "viewer")
    peer.websocket.send_json.assert_awaited_once_with({"status": "role_changed", "role": "viewer"})
    await manager.change_role(uuid.uuid4(), peer.user_id, None)
    peer.role = "editor"
    room.failed_since = time.monotonic() - 31
    doc = Doc()
    doc.get("text", type=Text).insert(0, "Текст")
    await manager.process(room, peer, create_update_message(doc.get_update()))
    peer.websocket.close.assert_awaited_once_with(1013)
    assert not room.dirty


async def test_oversized_result_is_rejected_before_mutation(context):
    manager, room, peer, _, _ = context
    doc = Doc()
    doc.get("text", type=Text).insert(0, "x" * (5 * 1024 * 1024))
    await manager.process(room, peer, create_update_message(doc.get_update()))
    peer.websocket.close.assert_awaited_once_with(1009)
    assert not room.dirty


async def test_peer_send_handles_disconnect(context):
    _, _, peer, _, _ = context
    peer.websocket.send_bytes.side_effect = RuntimeError()
    await peer.send(b"data")
    peer.websocket.send_json.side_effect = TimeoutError()
    await peer.send({"status": "saved"})


async def test_shutdown_flushes_dirty_room(context):
    manager, room, peer, session, _ = context
    room.dirty = True
    await manager.stop()
    session.commit.assert_awaited_once()
    peer.websocket.close.assert_awaited_once_with(1000)
