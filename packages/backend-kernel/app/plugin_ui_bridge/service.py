from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, cast
import uuid

from fastapi import WebSocket

from app.config import Config
from app.utils.logger import get_logger

from .connection_registry import BridgeConnectionRegistry
from .errors import PluginUIBridgeError
from .models import (
    BridgeEvent,
    BridgeMessageType,
    BridgeOperation,
    BridgeRequest,
    make_event_envelope,
    make_request_envelope,
)
from .pending_store import BridgePendingStore

logger = get_logger("plugin_ui_bridge_service")


@dataclass(slots=True)
class BridgeDispatchResult:
    request_id: str
    op: BridgeOperation
    result: Dict[str, Any]


class PluginUIBridgeService:
    def __init__(self) -> None:
        self._connections = BridgeConnectionRegistry()
        self._pending = BridgePendingStore()

    async def register(self, plugin_id: str, websocket: WebSocket) -> None:
        await self._connections.bind(plugin_id, websocket)
        logger.info("[plugin_ui_bridge] registered plugin=%s", plugin_id)

    async def unregister(self, plugin_id: str, websocket: WebSocket) -> None:
        await self._connections.unbind(plugin_id, websocket)
        await self._pending.fail_by_plugin(
            plugin_id,
            {
                "ok": False,
                "error_code": "bridge_disconnected",
                "message": "plugin ui bridge disconnected",
            },
        )
        logger.info("[plugin_ui_bridge] unregistered plugin=%s", plugin_id)

    async def handle_client_message(self, plugin_id: str, payload: Dict[str, Any]) -> None:
        msg_type = str(payload.get("type") or "")
        if msg_type != BridgeMessageType.RESULT.value:
            return
        request_id = str(payload.get("requestId") or "").strip()
        if not request_id:
            return
        future, _ = await self._pending.pop(request_id)
        if future and not future.done():
            result_payload = payload.get("result")
            if isinstance(result_payload, dict):
                future.set_result(cast(Dict[str, Any], result_payload))
            else:
                future.set_result({})
        logger.debug("[plugin_ui_bridge] received result plugin=%s request=%s", plugin_id, request_id)

    async def describe(self, plugin_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return (await self.dispatch(plugin_id=plugin_id, op=BridgeOperation.DESCRIBE, payload=payload)).result

    async def query(self, plugin_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return (await self.dispatch(plugin_id=plugin_id, op=BridgeOperation.QUERY, payload=payload)).result

    async def act(self, plugin_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return (await self.dispatch(plugin_id=plugin_id, op=BridgeOperation.ACT, payload=payload)).result

    async def scroll(self, plugin_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return (await self.dispatch(plugin_id=plugin_id, op=BridgeOperation.SCROLL, payload=payload)).result

    async def capabilities_list(self, plugin_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return (
            await self.dispatch(
                plugin_id=plugin_id,
                op=BridgeOperation.CAPABILITIES_LIST,
                payload=payload,
            )
        ).result

    async def capability_invoke(self, plugin_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return (
            await self.dispatch(
                plugin_id=plugin_id,
                op=BridgeOperation.CAPABILITY_INVOKE,
                payload=payload,
            )
        ).result

    async def push_context(self, plugin_id: str, payload: Dict[str, Any]) -> None:
        await self.push_event(plugin_id=plugin_id, event=BridgeEvent.CONTEXT_PUSH, payload=payload)

    async def resolve_connected_plugin_id(self, plugin_id: str) -> str:
        plugin_key = str(plugin_id or "").strip()
        if not plugin_key:
            return ""
        if await self._connections.get(plugin_key):
            return plugin_key
        safe_key = self._safe_plugin_key(plugin_key)
        plugin_ids = await self._connections.list_plugin_ids()
        for candidate in plugin_ids:
            if self._safe_plugin_key(candidate) == safe_key:
                return candidate
        return plugin_key

    async def push_event(self, plugin_id: str, event: BridgeEvent, payload: Dict[str, Any]) -> None:
        resolved_plugin_id = await self.resolve_connected_plugin_id(plugin_id)
        connection = await self._connections.get(resolved_plugin_id)
        if not connection:
            raise PluginUIBridgeError(
                code="bridge_not_connected",
                message=f"plugin bridge not connected: {plugin_id}",
            )
        envelope = make_event_envelope(plugin_id=resolved_plugin_id, event=event, payload=payload)
        async with connection.send_lock:
            await connection.websocket.send_json(envelope)

    async def dispatch(
        self,
        plugin_id: str,
        op: BridgeOperation,
        payload: Dict[str, Any],
    ) -> BridgeDispatchResult:
        resolved_plugin_id = await self.resolve_connected_plugin_id(plugin_id)
        connection = await self._connections.get(resolved_plugin_id)
        if not connection:
            raise PluginUIBridgeError(
                code="bridge_not_connected",
                message=f"plugin bridge not connected: {plugin_id}",
            )
        request_id = f"req_{uuid.uuid4().hex[:16]}"
        future = await self._pending.create(request_id, {"plugin_id": resolved_plugin_id, "op": op})
        envelope = make_request_envelope(
            BridgeRequest(
                request_id=request_id,
                plugin_id=resolved_plugin_id,
                op=op,
                payload=payload,
            )
        )
        async with connection.send_lock:
            await connection.websocket.send_json(envelope)
        timeout_seconds = self._resolve_dispatch_timeout_seconds(op=op, payload=payload)
        try:
            result = await asyncio.wait_for(future, timeout=timeout_seconds)
            if not isinstance(result, dict):
                result = {
                    "ok": False,
                    "error_code": "bridge_invalid_payload",
                    "message": "invalid bridge payload",
                }
            return BridgeDispatchResult(request_id=request_id, op=op, result=result)
        except asyncio.TimeoutError as err:
            pending_future, _ = await self._pending.pop(request_id)
            if pending_future and not pending_future.done():
                pending_future.cancel()
            raise PluginUIBridgeError(
                code="bridge_timeout",
                message=f"plugin ui bridge timeout: {op.value}",
            ) from err

    @staticmethod
    def _resolve_dispatch_timeout_seconds(op: BridgeOperation, payload: Dict[str, Any]) -> float:
        base_timeout_seconds = max(float(Config.PLUGIN_UI_BRIDGE_TIMEOUT_SECONDS), 1.0)
        if op != BridgeOperation.CAPABILITY_INVOKE:
            return base_timeout_seconds
        function_name = str(payload.get("function") or "").strip()
        if function_name not in {"assistant.event.wait", "assistant.session.wait_for_end"}:
            return base_timeout_seconds
        nested_payload = payload.get("payload")
        wait_payload = nested_payload if isinstance(nested_payload, dict) else {}
        raw_timeout_ms = wait_payload.get("timeout_ms")
        requested_timeout_seconds: float | None = None
        if isinstance(raw_timeout_ms, (int, float)) and not isinstance(raw_timeout_ms, bool):
            requested_timeout_seconds = max(float(raw_timeout_ms) / 1000.0, 0.0)
        buffer_seconds = max(float(Config.PLUGIN_UI_BRIDGE_SESSION_WAIT_TIMEOUT_BUFFER_SECONDS), 0.0)
        session_wait_timeout_seconds = max(float(Config.PLUGIN_UI_BRIDGE_SESSION_WAIT_TIMEOUT_SECONDS), 1.0)
        if requested_timeout_seconds is None:
            return max(base_timeout_seconds, session_wait_timeout_seconds)
        return max(base_timeout_seconds, session_wait_timeout_seconds, requested_timeout_seconds + buffer_seconds)

    @staticmethod
    def _safe_plugin_key(plugin_id: str) -> str:
        return str(plugin_id or "").strip().replace("/", "_").replace(".", "_")


_bridge_service: PluginUIBridgeService | None = None


def get_plugin_ui_bridge_service() -> PluginUIBridgeService:
    global _bridge_service
    if _bridge_service is None:
        _bridge_service = PluginUIBridgeService()
    return _bridge_service
