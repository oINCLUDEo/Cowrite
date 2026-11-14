"""Доступ к комнатам и сериализация REST-изменений с CRDT-операциями."""

import asyncio
import uuid
from typing import Annotated

from fastapi import Depends, Request

from app.modules.collab.rooms import RoomManager


def get_rooms(request: Request) -> RoomManager | None:
    return getattr(request.app.state, "rooms", None)


Rooms = Annotated[RoomManager | None, Depends(get_rooms)]


def mutation_lock(manager: RoomManager | None, document_id: uuid.UUID) -> asyncio.Lock:
    return manager.document_lock(document_id) if manager else asyncio.Lock()
