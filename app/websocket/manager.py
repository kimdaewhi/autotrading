from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """
    _summary_
    웹소켓 연결 관리 클래스
    _description_
    웹소켓 연결을 관리하는 클래스. 연결된 클라이언트 목록을 유지하고, 메시지를 브로드캐스트하는 기능을 제공
    """
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()
    
    
    # ⚙️ 클라이언트 연결 수락 및 목록에 추가
    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
    
    
    # ⚙️ 클라이언트 연결 종료 및 목록에서 제거
    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
    
    
    # ⚙️ 특정 클라이언트에게 JSON 메시지 전송
    async def send_json(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        await websocket.send_json(message)
    
    
    # ⚙️ 모든 연결된 클라이언트에게 JSON 메시지 브로드캐스트
    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            connections = list(self._connections)
        
        dead_connections: list[WebSocket] = []
        
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        
        # 연결이 끊긴 클라이언트는 목록에서 제거
        if dead_connections:
            async with self._lock:
                for connection in dead_connections:
                    self._connections.discard(connection)
    
    
    # ⚙️ 주문 업데이트 이벤트 브로드캐스트
    async def broadcast_order_updated(self, order_data: dict[str, Any]) -> None:
        await self.broadcast(
            {
                "type": "order_updated",
                "data": order_data,
            }
        )
    
    
    # ⚙️ 주문 생성 이벤트 브로드캐스트
    async def broadcast_order_created(self, order_data: dict[str, Any]) -> None:
        await self.broadcast(
            {
                "type": "order_created",
                "data": order_data,
            }
        )


ws_manager = ConnectionManager()