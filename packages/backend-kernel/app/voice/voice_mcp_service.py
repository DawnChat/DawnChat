from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from app.plugin_ui_bridge.errors import PluginUIBridgeError
from app.plugin_ui_bridge.models import BridgeEvent
from app.plugin_ui_bridge.service import PluginUIBridgeService, get_plugin_ui_bridge_service
from app.services.plugin_id_resolver import PluginIdResolveError, get_plugin_id_resolver
from app.utils.logger import get_logger

from .runtime_service import TtsRuntimeService, get_tts_runtime_service

logger = get_logger("voice_mcp_service")


@dataclass(frozen=True, slots=True)
class VoiceToolDefinition:
    name: str
    description: str
    input_schema: Dict[str, Any]


class VoiceMcpService:
    def __init__(
        self,
        runtime_service: TtsRuntimeService | None = None,
        bridge_service: PluginUIBridgeService | None = None,
    ) -> None:
        self._runtime = runtime_service or get_tts_runtime_service()
        self._bridge = bridge_service or get_plugin_ui_bridge_service()
        self._defs = self._build_definitions()

    def tool_definitions(self) -> List[VoiceToolDefinition]:
        return list(self._defs.values())

    async def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._defs.get(name)
        if tool is None:
            return {"ok": False, "error_code": "tool_not_found", "message": f"unknown tool: {name}"}
        try:
            if name == "dawnchat.voice.speak":
                plugin_id = await self._resolve_plugin_id(str(arguments.get("plugin_id") or "").strip())
                text = str(arguments.get("text") or "").strip()
                voice = str(arguments.get("voice") or "").strip()
                sid = self._normalize_sid(arguments.get("sid"))
                mode = str(arguments.get("mode") or "manual").strip().lower() or "manual"
                engine = str(arguments.get("engine") or "python").strip().lower() or "python"
                interrupt = bool(arguments.get("interrupt", False))
                task_id = await self._runtime.submit_speak(
                    plugin_id=plugin_id,
                    text=text,
                    voice=voice,
                    sid=sid,
                    mode=mode,
                    engine=engine,
                    interrupt=interrupt,
                )
                stream_url = f"/api/tts/stream/{task_id}"
                status_url = f"/api/tts/tasks/{task_id}"
                await self._notify_bridge(
                    plugin_id=plugin_id,
                    event=BridgeEvent.TTS_SPEAK_ACCEPTED,
                    payload={
                        "plugin_id": plugin_id,
                        "task_id": task_id,
                        "stream_url": stream_url,
                        "status_url": status_url,
                        "mode": mode,
                        "source": "voice_mcp",
                    },
                )
                return {
                    "ok": True,
                    "data": {
                        "task_id": task_id,
                        "stream_url": stream_url,
                        "status_url": status_url,
                    },
                }
            if name == "dawnchat.voice.stop":
                stop_task_id: str | None = str(arguments.get("task_id") or "").strip() or None
                stop_plugin_id: str | None = str(arguments.get("plugin_id") or "").strip() or None
                if stop_plugin_id:
                    stop_plugin_id = await self._resolve_plugin_id(stop_plugin_id)
                resolved_plugin_id = stop_plugin_id
                if not resolved_plugin_id and stop_task_id:
                    task = self._runtime.get_task(stop_task_id)
                    if isinstance(task, dict):
                        resolved_plugin_id = str(task.get("plugin_id") or "").strip() or None
                stopped = await self._runtime.stop(task_id=stop_task_id, plugin_id=stop_plugin_id)
                if stopped:
                    await self._notify_bridge(
                        plugin_id=resolved_plugin_id,
                        event=BridgeEvent.TTS_STOPPED,
                        payload={
                            "plugin_id": resolved_plugin_id or "",
                            "task_id": stop_task_id or "",
                            "stopped": True,
                            "source": "voice_mcp",
                        },
                    )
                return {"ok": True, "data": {"stopped": bool(stopped)}}
            if name == "dawnchat.voice.status":
                task_id = str(arguments.get("task_id") or "").strip()
                if task_id:
                    task = self._runtime.get_task(task_id)
                    if task is None:
                        return {"ok": False, "error_code": "task_not_found", "message": f"task not found: {task_id}"}
                    return {"ok": True, "data": {"task": task}}
                plugin_id = await self._resolve_plugin_id(str(arguments.get("plugin_id") or "").strip())
                return {"ok": True, "data": self._runtime.get_plugin_runtime_state(plugin_id)}
        except ValueError as err:
            return {"ok": False, "error_code": "invalid_arguments", "message": str(err)}
        except Exception as err:
            return {"ok": False, "error_code": "voice_runtime_error", "message": str(err)}
        return {"ok": False, "error_code": "tool_not_found", "message": f"unknown tool: {name}"}

    @staticmethod
    def _build_definitions() -> Dict[str, VoiceToolDefinition]:
        defs = [
            VoiceToolDefinition(
                name="dawnchat.voice.speak",
                description="Synthesize TTS audio for plugin assistant response and enqueue playback segments",
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                        "text": {"type": "string"},
                        "voice": {"type": "string"},
                        "sid": {"type": "integer", "minimum": 0},
                        "mode": {"type": "string", "enum": ["manual"], "default": "manual"},
                        "engine": {"type": "string", "enum": ["python", "azure", "dawn-tts"], "default": "python"},
                        "interrupt": {"type": "boolean", "default": False},
                    },
                    "required": ["plugin_id", "text"],
                },
            ),
            VoiceToolDefinition(
                name="dawnchat.voice.stop",
                description="Stop active TTS task by task_id or plugin_id",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "plugin_id": {"type": "string"},
                    },
                },
            ),
            VoiceToolDefinition(
                name="dawnchat.voice.status",
                description="Get TTS task status or plugin-level TTS runtime status",
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "plugin_id": {"type": "string"},
                    },
                },
            ),
        ]
        return {item.name: item for item in defs}

    @staticmethod
    def _normalize_sid(raw: Any) -> int | None:
        if raw is None:
            return None
        if isinstance(raw, bool):
            raise ValueError("sid must be integer")
        value = int(raw)
        if value < 0:
            raise ValueError("sid must be >= 0")
        return value

    async def _notify_bridge(self, plugin_id: str | None, event: BridgeEvent, payload: Dict[str, Any]) -> None:
        plugin_key = str(plugin_id or "").strip()
        if not plugin_key:
            return
        task_id = str(payload.get("task_id") or "").strip()
        logger.info("voice_bridge_notify_start plugin=%s event=%s task_id=%s", plugin_key, event.value, task_id)
        try:
            await self._bridge.push_event(plugin_key, event, payload)
            await self._record_bridge_observability(plugin_id=plugin_key, ok=True)
            logger.info("voice_bridge_notify_success plugin=%s event=%s task_id=%s", plugin_key, event.value, task_id)
        except PluginUIBridgeError as err:
            await self._record_bridge_observability(plugin_id=plugin_key, ok=False, error_code=err.code)
            logger.warning(
                "voice_bridge_notify_failed plugin=%s event=%s task_id=%s code=%s message=%s",
                plugin_key,
                event.value,
                task_id,
                err.code,
                err.message,
            )
        except Exception as err:
            await self._record_bridge_observability(plugin_id=plugin_key, ok=False, error_code="unknown_error")
            logger.warning(
                "voice_bridge_notify_failed_unknown plugin=%s event=%s task_id=%s error=%s",
                plugin_key,
                event.value,
                task_id,
                str(err),
            )

    async def _record_bridge_observability(self, *, plugin_id: str, ok: bool, error_code: str = "") -> None:
        recorder = getattr(self._runtime, "record_bridge_notify", None)
        if not callable(recorder):
            return
        await recorder(plugin_id=plugin_id, ok=ok, error_code=error_code)

    async def _resolve_plugin_id(self, plugin_id: str) -> str:
        plugin_key = str(plugin_id or "").strip()
        if not plugin_key:
            return ""
        try:
            resolved = get_plugin_id_resolver().resolve(plugin_key)
            return resolved.canonical_plugin_id
        except PluginIdResolveError:
            pass
        resolver = getattr(self._bridge, "resolve_connected_plugin_id", None)
        if not callable(resolver):
            return plugin_key
        try:
            resolved = await resolver(plugin_key)
        except Exception:
            return plugin_key
        resolved_key = str(resolved or "").strip()
        return resolved_key or plugin_key


_voice_mcp_service: VoiceMcpService | None = None


def get_voice_mcp_service() -> VoiceMcpService:
    global _voice_mcp_service
    if _voice_mcp_service is None:
        _voice_mcp_service = VoiceMcpService()
    return _voice_mcp_service
