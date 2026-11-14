"""Бинарный CRDT и отдельный канал подтверждений сохранения."""

from uuid import UUID

from fastapi import APIRouter, WebSocket

from app.modules.collab.rooms import RoomManager

router = APIRouter()


@router.websocket("/ws/documents/{document_id}")
async def collaborate(websocket: WebSocket, document_id: UUID) -> None:
    manager: RoomManager = websocket.app.state.rooms
    await manager.serve(websocket, document_id)


@router.websocket("/ws/documents/{document_id}/status")
async def status(websocket: WebSocket, document_id: UUID) -> None:
    manager: RoomManager = websocket.app.state.rooms
    await manager.serve(websocket, document_id, status=True)
