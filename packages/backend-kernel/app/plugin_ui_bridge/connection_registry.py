from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from fastapi import WebSocket


@dataclass(slots=True)
class BridgeConnection:
    plugin_id: str
    websocket: WebSocket
    connected_at: datetime = field(default_factory=datetime.utcnow)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class BridgeConnectionRegistry:
    def __init__(self) -> None:
        self._connections: Dict[str, BridgeConnection] = {}
        self._lock = asyncio.Lock()

    async def bind(self, plugin_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[plugin_id] = BridgeConnection(plugin_id=plugin_id, websocket=websocket)

    async def unbind(self, plugin_id: str, websocket: Optional[WebSocket] = None) -> None:
        async with self._lock:
            conn = self._connections.get(plugin_id)
            if not conn:
                return
            if websocket is not None and conn.websocket is not websocket:
                return
            self._connections.pop(plugin_id, None)

    async def get(self, plugin_id: str) -> Optional[BridgeConnection]:
        async with self._lock:
            return self._connections.get(plugin_id)

    async def list_plugin_ids(self) -> list[str]:
        async with self._lock:
            return list(self._connections.keys())

