"""Адаптер FastAPI WebSocket к интерфейсу канала pycrdt-websocket."""

from typing import Self

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState


class WebSocketChannel:
    def __init__(self, websocket: WebSocket, path: str) -> None:
        self.websocket = websocket
        self.path = path

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> bytes:
        try:
            return await self.recv()
        except WebSocketDisconnect:
            # Обычное отключение завершает чтение, а не роняет CRDT-комнату.
            raise StopAsyncIteration from None

    async def recv(self) -> bytes:
        message = await self.websocket.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(message.get("code", 1000))
        data: bytes | None = message.get("bytes")
        if data is None:
            # Yjs передаёт бинарные сообщения. JSON и обычный текст здесь не принимаем.
            await self.websocket.close(code=1003, reason="Binary protocol required")
            raise WebSocketDisconnect(1003)
        return data

    async def send(self, message: bytes) -> None:
        try:
            await self.websocket.send_bytes(message)
        except (WebSocketDisconnect, OSError):
            # Клиент мог отключиться между началом рассылки и фактической отправкой.
            return
        except RuntimeError:
            # Не скрываем ошибки кода, если соединение ещё открыто.
            if self.websocket.application_state != WebSocketState.CONNECTED:
                return
            raise
