from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional


class BridgePendingStore:
    def __init__(self) -> None:
        self._pending: Dict[str, asyncio.Future[Dict[str, Any]]] = {}
        self._meta: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def create(self, request_id: str, meta: Dict[str, Any]) -> asyncio.Future[Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Dict[str, Any]] = loop.create_future()
        async with self._lock:
            self._pending[request_id] = future
            self._meta[request_id] = dict(meta)
        return future

    async def pop(self, request_id: str) -> tuple[Optional[asyncio.Future[Dict[str, Any]]], Dict[str, Any]]:
        async with self._lock:
            future = self._pending.pop(request_id, None)
            meta = self._meta.pop(request_id, {})
            return future, meta

    async def fail_by_plugin(self, plugin_id: str, error_payload: Dict[str, Any]) -> None:
        async with self._lock:
            request_ids = [rid for rid, meta in self._meta.items() if str(meta.get("plugin_id")) == plugin_id]
            futures = [self._pending.pop(rid, None) for rid in request_ids]
            for rid in request_ids:
                self._meta.pop(rid, None)
        for future in futures:
            if future and not future.done():
                future.set_result(error_payload)

