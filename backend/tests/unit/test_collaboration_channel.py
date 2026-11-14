from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.modules.collab.service import WebSocketChannel


async def test_channel_iteration_and_binary_receive():
    websocket = AsyncMock()
    websocket.receive.side_effect = [
        {"type": "websocket.receive", "bytes": b"update"},
        {"type": "websocket.disconnect", "code": 1000},
    ]
    channel = WebSocketChannel(websocket, "room")
    assert [message async for message in channel] == [b"update"]


async def test_channel_rejects_text():
    websocket = AsyncMock()
    websocket.receive.return_value = {"type": "websocket.receive", "text": "invalid"}
    with pytest.raises(WebSocketDisconnect):
        await WebSocketChannel(websocket, "room").recv()
    websocket.close.assert_awaited_once_with(code=1003, reason="Binary protocol required")


@pytest.mark.parametrize("error", [WebSocketDisconnect(), OSError("peer closed")])
async def test_broadcast_ignores_disconnected_peer(error):
    websocket = AsyncMock()
    websocket.send_bytes.side_effect = error
    await WebSocketChannel(websocket, "room").send(b"data")


async def test_broadcast_ignores_runtime_error_after_close():
    websocket = AsyncMock()
    websocket.send_bytes.side_effect = RuntimeError("already closed")
    websocket.application_state = WebSocketState.DISCONNECTED
    await WebSocketChannel(websocket, "room").send(b"data")


async def test_broadcast_does_not_hide_unexpected_runtime_error():
    websocket = AsyncMock()
    websocket.send_bytes.side_effect = RuntimeError("unexpected bug")
    websocket.application_state = WebSocketState.CONNECTED
    with pytest.raises(RuntimeError, match="unexpected bug"):
        await WebSocketChannel(websocket, "room").send(b"data")
