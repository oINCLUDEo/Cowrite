"""Комнаты с общей блокировкой для синхронизации, сохранения и отката."""

import asyncio
import contextlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import jwt
from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from pycrdt import (
    Awareness,
    Doc,
    create_awareness_message,
    create_sync_message,
    create_update_message,
    handle_sync_message,
    read_message,
)
from sqlalchemy import select

from app.core.config import Settings
from app.core.db import Database
from app.core.metrics import save_errors, ws_connections
from app.core.security import decode_access_token
from app.modules.auth.models import User
from app.modules.documents.models import Document
from app.modules.documents.service import require_role

logger = logging.getLogger(__name__)


@dataclass(eq=False)
class Peer:
    websocket: WebSocket
    user_id: uuid.UUID
    token: str
    role: str
    status: bool = False
    active: bool = True
    awareness_ids: set[int] = field(default_factory=set)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, value: bytes | dict[str, object]) -> None:
        async with self.send_lock:
            try:
                if isinstance(value, bytes):
                    await asyncio.wait_for(self.websocket.send_bytes(value), 5)
                else:
                    await asyncio.wait_for(self.websocket.send_json(value), 5)
            except (RuntimeError, WebSocketDisconnect, TimeoutError):
                pass


class Room:
    def __init__(self, document: Document) -> None:
        self.id = document.id
        self.generation = document.generation
        self.revision = document.state_revision
        self.doc: Doc[Any] = Doc()
        self.doc.apply_update(document.ydoc_state)
        self.awareness = Awareness(self.doc)
        self.awareness.set_local_state(None)
        self.lock = asyncio.Lock()
        self.peers: set[Peer] = set()
        self.dirty = False
        self.changed_at = 0.0
        self.first_dirty = 0.0
        self.failed_since: float | None = None

    async def broadcast(self, message: bytes) -> None:
        await asyncio.gather(*(peer.send(message) for peer in tuple(self.peers) if not peer.status))

    async def notify(self) -> None:
        value: dict[str, object] = {
            "status": "error" if self.failed_since else "unsaved" if self.dirty else "saved",
            "revision": self.revision,
            "generation": self.generation,
        }
        await asyncio.gather(
            *(peer.send({**value, "role": peer.role}) for peer in tuple(self.peers) if peer.status)
        )


class RoomManager:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.rooms: dict[uuid.UUID, Room] = {}
        self.locks: dict[uuid.UUID, asyncio.Lock] = {}
        self.registry_lock = asyncio.Lock()
        self.task: asyncio.Task[None] | None = None

    def document_lock(self, document_id: uuid.UUID) -> asyncio.Lock:
        # Блокировки не удаляются вместе с комнатой: ожидающий запрос использует ту же.
        return self.locks.setdefault(document_id, asyncio.Lock())

    async def start(self) -> None:
        self.task = asyncio.create_task(self.maintenance())

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task

        async def flush_all() -> None:
            for room in tuple(self.rooms.values()):
                async with self.document_lock(room.id):
                    await self.save(room)
                    await self.close_peers(room, 1000)

        try:
            await asyncio.wait_for(flush_all(), 30)
        except TimeoutError:
            logger.error("Room shutdown flush timed out")

    async def save(self, room: Room) -> bool:
        if not room.dirty:
            return True
        try:
            async with self.database.sessions() as session:
                document = await session.scalar(
                    select(Document).where(Document.id == room.id).with_for_update()
                )
                if document is None or document.generation != room.generation:
                    await self.close_peers(room, 4404 if document is None else 4409)
                    room.dirty = False
                    return False
                document.ydoc_state = room.doc.get_update()
                document.state_revision += 1
                await session.commit()
                room.revision = document.state_revision
            room.dirty = False
            room.failed_since = None
            await room.notify()
            return True
        except Exception:
            save_errors.inc()
            room.failed_since = room.failed_since or time.monotonic()
            logger.warning("Document save failed", extra={"document_id": str(room.id)})
            await room.notify()
            return False

    async def maintenance(self) -> None:
        while True:
            await asyncio.sleep(1)
            now = time.monotonic()
            for room in tuple(self.rooms.values()):
                async with self.document_lock(room.id):
                    for peer in tuple(room.peers):
                        try:
                            decode_access_token(peer.token, self.settings)
                        except (jwt.InvalidTokenError, HTTPException):
                            await self.close_peer(peer, 4401)
                    if room.dirty and (now - room.changed_at >= 2 or now - room.first_dirty >= 10):
                        await self.save(room)
                    if not room.peers and not room.dirty:
                        self.rooms.pop(room.id, None)

    async def close_peer(self, peer: Peer, code: int) -> None:
        # Уже полученное сообщение не должно применяться после отзыва доступа.
        peer.active = False
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await peer.websocket.close(code)

    async def close_peers(self, room: Room, code: int, user_id: uuid.UUID | None = None) -> None:
        await asyncio.gather(
            *(
                self.close_peer(peer, code)
                for peer in tuple(room.peers)
                if user_id is None or peer.user_id == user_id
            )
        )

    async def change_role(
        self, document_id: uuid.UUID, user_id: uuid.UUID, role: str | None
    ) -> None:
        room = self.rooms.get(document_id)
        if room:
            for peer in tuple(room.peers):
                if peer.user_id == user_id:
                    if role is None:
                        await self.close_peer(peer, 4403)
                    else:
                        peer.role = role
                        if peer.status:
                            await peer.send({"status": "role_changed", "role": role})

    async def serve(
        self, websocket: WebSocket, document_id: uuid.UUID, status: bool = False
    ) -> None:
        await websocket.accept()
        if websocket.headers.get("origin") not in self.settings.allowed_origins:
            await websocket.close(4403)
            return
        token = websocket.query_params.get("token", "")
        try:
            user_id = decode_access_token(token, self.settings)
        except (jwt.InvalidTokenError, HTTPException):
            await websocket.close(4401)
            return
        peer: Peer | None = None
        room: Room | None = None
        try:
            async with self.document_lock(document_id):
                async with self.database.sessions() as session:
                    session.info["role_cache"] = getattr(websocket.app.state, "role_cache", None)
                    if await session.get(User, user_id) is None:
                        await websocket.close(4401)
                        return
                    document, role = await require_role(session, document_id, user_id)
                    if websocket.query_params.get("generation") != str(document.generation):
                        await websocket.close(4409)
                        return
                    room = self.rooms.get(document_id)
                    if room is None:
                        room = Room(document)
                        self.rooms[document_id] = room
                async with self.registry_lock:
                    count = sum(
                        sum(p.status == status for p in r.peers) for r in self.rooms.values()
                    )
                    per_room = sum(not p.status for p in room.peers)
                    same_user = sum(p.status and p.user_id == user_id for p in room.peers)
                    same_user_crdt = sum(not p.status and p.user_id == user_id for p in room.peers)
                    if (
                        count >= 50
                        or (not status and per_room >= 10)
                        or (status and same_user >= same_user_crdt)
                    ):
                        await websocket.close(4429)
                        return
                    peer = Peer(websocket, user_id, token, role, status)
                    room.peers.add(peer)
                    if not status:
                        ws_connections.inc()
                if status:
                    await room.notify()
                else:
                    await peer.send(create_sync_message(room.doc))
                    if room.awareness.states:
                        await peer.send(
                            create_awareness_message(
                                room.awareness.encode_awareness_update(list(room.awareness.states))
                            )
                        )
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                async with self.document_lock(document_id):
                    if not peer.active or self.rooms.get(document_id) is not room:
                        break
                    try:
                        decode_access_token(token, self.settings)
                    except (jwt.InvalidTokenError, HTTPException):
                        await websocket.close(4401)
                        break
                    if status:
                        # Управляющий канал только передаёт серверные подтверждения.
                        continue
                    payload = message.get("bytes")
                    if payload is None:
                        await websocket.close(1003)
                        break
                    if len(payload) > 1024 * 1024:
                        await websocket.close(1009)
                        break
                    await self.process(room, peer, payload)
        except HTTPException as error:
            await websocket.close(4404 if error.status_code == 404 else 4403)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            if room and peer:
                async with self.document_lock(document_id):
                    room.peers.discard(peer)
                    if peer.awareness_ids:
                        room.awareness.remove_awareness_states(list(peer.awareness_ids), peer)
                        await room.broadcast(
                            create_awareness_message(
                                room.awareness.encode_awareness_update(list(peer.awareness_ids))
                            )
                        )
                    if not status:
                        ws_connections.dec()
                    if not any(not p.status for p in room.peers):
                        await self.save(room)

    async def process(self, room: Room, peer: Peer, payload: bytes) -> None:
        if not peer.active:
            return
        try:
            if not payload:
                raise ValueError("Empty message")
            if payload[0] == 0:
                if len(payload) < 2 or payload[1] not in (0, 1, 2):
                    raise ValueError("Invalid sync type")
                if payload[1] == 0:
                    reply = handle_sync_message(payload[1:], room.doc)
                    if reply:
                        await peer.send(reply)
                elif peer.role != "viewer":
                    if room.failed_since and time.monotonic() - room.failed_since >= 30:
                        await self.close_peer(peer, 1013)
                        return
                    # Проверяем состояние на копии, прежде чем менять общую комнату.
                    candidate: Doc[Any] = Doc()
                    candidate.apply_update(room.doc.get_update())
                    handle_sync_message(payload[1:], candidate)
                    state = candidate.get_update()
                    if len(state) > 5 * 1024 * 1024:
                        await self.close_peer(peer, 1009)
                        return
                    if state != room.doc.get_update():
                        room.doc.apply_update(read_message(payload[2:]))
                        now = time.monotonic()
                        if not room.dirty:
                            room.first_dirty = now
                        room.dirty = True
                        room.changed_at = now
                        await room.broadcast(create_update_message(read_message(payload[2:])))
                        await room.notify()
            elif payload[0] == 1:
                previous = {key: value.copy() for key, value in room.awareness.meta.items()}
                room.awareness.apply_awareness_update(read_message(payload[1:]), peer)
                peer.awareness_ids.update(
                    key for key, value in room.awareness.meta.items() if value != previous.get(key)
                )
                await room.broadcast(payload)
            elif payload[0] == 3:
                if room.awareness.states:
                    await peer.send(
                        create_awareness_message(
                            room.awareness.encode_awareness_update(list(room.awareness.states))
                        )
                    )
            else:
                raise ValueError("Invalid protocol message")
        except (ValueError, IndexError, TypeError, KeyError):
            await self.close_peer(peer, 1003)
