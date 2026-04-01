from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket.manager import ws_manager

router = APIRouter()


@router.websocket("/ws/orders")
async def orders_websocket(websocket: WebSocket) -> None:
    await ws_manager.connect(websocket)

    try:
        await ws_manager.send_json(
            websocket,
            {
                "type": "connected",
                "message": "orders websocket connected",
            },
        )

        while True:
            # 클라이언트 ping / keep-alive 용
            # 클라이언트가 아무 메시지도 안 보내면
            # 아래 대신 asyncio.sleep 루프로 바꿔도 됨
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
            except asyncio.TimeoutError:
                await ws_manager.send_json(websocket, {"type": "ping"})
                continue

            if isinstance(message, dict) and message.get("type") == "pong":
                continue

    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)
    except Exception:
        await ws_manager.disconnect(websocket)