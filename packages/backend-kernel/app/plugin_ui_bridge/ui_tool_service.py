from __future__ import annotations

from dataclasses import dataclass
import json
from time import perf_counter
from typing import Any, Dict, List, Tuple

from app.config import Config
from app.plugins import get_plugin_manager
from app.plugins.lifecycle_service import get_plugin_lifecycle_service
from app.services.plugin_id_resolver import PluginIdResolveError, get_plugin_id_resolver

from .artifact_store import UiArtifactStore
from .errors import PluginUIBridgeError
from .models import BridgeOperation
from .service import PluginUIBridgeService, get_plugin_ui_bridge_service


@dataclass(frozen=True, slots=True)
class UiToolDefinition:
    name: str
    description: str
    op: BridgeOperation
    input_schema: Dict[str, Any]
    capability_function: str | None = None


class UiToolService:
    _ACT_TARGET_REQUIRED_ANY: Tuple[str, ...] = ("nodeId", "pathIndex", "selector", "bounds", "textContains")
    _DESCRIBE_SCOPE_ALLOWED: Tuple[str, ...] = ("all", "visible", "viewport")
    _DESCRIPTION_MAX_LENGTH: int = 120

    def __init__(
        self,
        bridge_service: PluginUIBridgeService | None = None,
        artifact_store: UiArtifactStore | None = None,
    ) -> None:
        self._bridge = bridge_service or get_plugin_ui_bridge_service()
        self._artifact_store = artifact_store or UiArtifactStore()
        self._defs = self._build_definitions()

    def tool_definitions(self) -> List[UiToolDefinition]:
        return list(self._defs.values())

    async def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._defs.get(name)
        if not tool:
            raise PluginUIBridgeError(code="tool_not_found", message=f"unknown tool: {name}")

        plugin_id = str(arguments.get("plugin_id") or "").strip()
        if not plugin_id:
            raise PluginUIBridgeError(code="missing_plugin_id", message="plugin_id is required")
        plugin_id = self._resolve_plugin_id(plugin_id)

        payload = self._normalize_tool_payload(tool, arguments)
        display_title, display_source = self._resolve_display_title(tool, payload)
        if tool.op == BridgeOperation.RUNTIME_INFO:
            started = perf_counter()
            manager = get_plugin_manager()
            runtime_info = manager.get_plugin_runtime_info(plugin_id)
            if runtime_info is None:
                raise PluginUIBridgeError(code="plugin_not_found", message=f"plugin not found: {plugin_id}")
            elapsed_ms = int((perf_counter() - started) * 1000)
            return self._build_local_response(
                op=tool.op,
                data=runtime_info,
                elapsed_ms=elapsed_ms,
                display_title=display_title,
                display_source=display_source,
            )
        if tool.op == BridgeOperation.RUNTIME_RESTART:
            started = perf_counter()
            manager = get_plugin_manager()
            if manager.get_plugin_snapshot(plugin_id) is None:
                raise PluginUIBridgeError(code="plugin_not_found", message=f"plugin not found: {plugin_id}")
            target = str(payload.get("target") or "dev_session")
            if target != "dev_session":
                raise PluginUIBridgeError(
                    code="invalid_arguments",
                    message="target must be 'dev_session'",
                )
            task_id = await get_plugin_lifecycle_service().submit_restart_dev_session(plugin_id)
            elapsed_ms = int((perf_counter() - started) * 1000)
            return self._build_local_response(
                op=tool.op,
                data={
                    "target": "dev_session",
                    "task_id": task_id,
                    "poll_url": f"http://127.0.0.1:{Config.API_PORT}/api/plugins/operations/{task_id}",
                },
                elapsed_ms=elapsed_ms,
                display_title=display_title,
                display_source=display_source,
            )
        if tool.op == BridgeOperation.CAPABILITIES_LIST:
            started = perf_counter()
            data = await self._build_capabilities_catalog(plugin_id)
            elapsed_ms = int((perf_counter() - started) * 1000)
            return self._build_local_response(
                op=tool.op,
                data=data,
                elapsed_ms=elapsed_ms,
                display_title=display_title,
                display_source=display_source,
            )
        started = perf_counter()
        dispatch_result = await self._bridge.dispatch(plugin_id=plugin_id, op=tool.op, payload=payload)
        elapsed_ms = int((perf_counter() - started) * 1000)

        artifact_result = self._artifact_store.write_result(
            plugin_id=plugin_id,
            request_id=dispatch_result.request_id,
            op=tool.op,
            result=dispatch_result.result,
        )

        ok = bool(dispatch_result.result.get("ok", True))
        response: Dict[str, Any] = {
            "ok": ok,
            "data": self._compact_data(tool.op, artifact_result.data),
            "artifacts": artifact_result.artifacts,
            "display": {
                "title": display_title,
                "source": display_source,
            },
            "debug": {
                "request_id": dispatch_result.request_id,
                "op": tool.op.value,
                "elapsed_ms": elapsed_ms,
            },
        }
        if not ok:
            response["error_code"] = str(dispatch_result.result.get("error_code") or "ui_bridge_failed")
            response["message"] = str(dispatch_result.result.get("message") or "ui bridge operation failed")
        return response

    @classmethod
    def _normalize_tool_payload(cls, tool: UiToolDefinition, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool.capability_function == "assistant.session.start":
            return cls._build_session_start_invoke_payload(arguments)
        if tool.capability_function == "assistant.session.status":
            return cls._build_session_status_invoke_payload(arguments)
        if tool.capability_function == "assistant.session.stop":
            return cls._build_session_stop_invoke_payload(arguments)
        if tool.capability_function == "assistant.event.wait":
            return cls._build_event_wait_invoke_payload(arguments)
        if tool.capability_function == "assistant.session.wait_for_end":
            return cls._build_session_wait_for_end_invoke_payload(arguments)
        return cls._validate_and_normalize_arguments(tool.op, arguments)

    @classmethod
    def _build_session_start_invoke_payload(cls, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload = {k: v for k, v in arguments.items() if k not in {"plugin_id", "options"}}
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list) or len(raw_steps) == 0:
            raise PluginUIBridgeError(code="invalid_arguments", message="steps must be a non-empty array")
        normalized_steps: List[Dict[str, Any]] = []
        for index, raw_step in enumerate(raw_steps):
            if not isinstance(raw_step, dict):
                raise PluginUIBridgeError(code="invalid_arguments", message=f"steps[{index}] must be an object")
            step_id = raw_step.get("id")
            if step_id is not None and (not isinstance(step_id, str) or not step_id.strip()):
                raise PluginUIBridgeError(code="invalid_arguments", message=f"steps[{index}].id must be a non-empty string")
            action = raw_step.get("action")
            if not isinstance(action, dict):
                raise PluginUIBridgeError(code="invalid_arguments", message=f"steps[{index}].action must be an object")
            action_type = str(action.get("type") or "").strip()
            if not action_type:
                raise PluginUIBridgeError(code="invalid_arguments", message=f"steps[{index}].action.type is required")
            raw_action_payload = action.get("payload")
            if raw_action_payload is None:
                action_payload: Dict[str, Any] = {}
            elif isinstance(raw_action_payload, dict):
                action_payload = {str(key): value for key, value in raw_action_payload.items()}
            else:
                raise PluginUIBridgeError(
                    code="invalid_arguments",
                    message=f"steps[{index}].action.payload must be an object",
                )
            if action_type == "view.capability.invoke":
                cls._assert_view_capability_invoke_payload_shape(
                    action_payload,
                    context=f"session.start steps[{index}] action view.capability.invoke",
                )
            normalized_step: Dict[str, Any] = {
                "action": {
                    "type": action_type,
                    "payload": action_payload,
                }
            }
            if isinstance(step_id, str) and step_id.strip():
                normalized_step["id"] = step_id.strip()
            timeout_ms = raw_step.get("timeout_ms")
            if timeout_ms is not None:
                parsed_timeout_ms = cls._normalize_non_negative_number(timeout_ms)
                if parsed_timeout_ms is None:
                    raise PluginUIBridgeError(
                        code="invalid_arguments",
                        message=f"steps[{index}].timeout_ms must be a non-negative number",
                    )
                normalized_step["timeout_ms"] = parsed_timeout_ms
            normalized_steps.append(normalized_step)
        session_payload: Dict[str, Any] = {
            "steps": normalized_steps,
        }
        return cls._validate_and_normalize_arguments(
            BridgeOperation.CAPABILITY_INVOKE,
            {
                "plugin_id": arguments.get("plugin_id"),
                "function": "assistant.session.start",
                "payload": session_payload,
                "options": arguments.get("options", {}),
                "description": arguments.get("description"),
                "title": arguments.get("title"),
            },
        )

    @classmethod
    def _build_session_stop_invoke_payload(cls, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_session_id = arguments.get("session_id")
        session_id = str(raw_session_id or "").strip()
        if not session_id:
            raise PluginUIBridgeError(code="invalid_arguments", message="session_id is required")
        raw_reason = arguments.get("reason")
        reason = str(raw_reason or "").strip()
        stop_payload: Dict[str, Any] = {
            "session_id": session_id,
        }
        if reason:
            stop_payload["reason"] = reason
        return cls._validate_and_normalize_arguments(
            BridgeOperation.CAPABILITY_INVOKE,
            {
                "plugin_id": arguments.get("plugin_id"),
                "function": "assistant.session.stop",
                "payload": stop_payload,
                "options": arguments.get("options", {}),
                "description": arguments.get("description"),
                "title": arguments.get("title"),
            },
        )

    @classmethod
    def _build_session_status_invoke_payload(cls, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_session_id = arguments.get("session_id")
        session_id = str(raw_session_id or "").strip()
        if not session_id:
            raise PluginUIBridgeError(code="invalid_arguments", message="session_id is required")
        return cls._validate_and_normalize_arguments(
            BridgeOperation.CAPABILITY_INVOKE,
            {
                "plugin_id": arguments.get("plugin_id"),
                "function": "assistant.session.status",
                "payload": {
                    "session_id": session_id,
                },
                "options": arguments.get("options", {}),
                "description": arguments.get("description"),
                "title": arguments.get("title"),
            },
        )

    @classmethod
    def _build_event_wait_invoke_payload(cls, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_event_types = arguments.get("event_types")
        if not isinstance(raw_event_types, list) or len(raw_event_types) == 0:
            raise PluginUIBridgeError(
                code="invalid_arguments",
                message="event_types must be a non-empty array",
            )
        event_types = [str(item).strip() for item in raw_event_types if isinstance(item, str) and item.strip()]
        if len(event_types) != len(raw_event_types):
            raise PluginUIBridgeError(
                code="invalid_arguments",
                message="event_types must contain non-empty strings",
            )
        wait_payload: Dict[str, Any] = {
            "event_types": event_types,
        }
        raw_match = arguments.get("match")
        if raw_match is not None:
            if not isinstance(raw_match, dict):
                raise PluginUIBridgeError(code="invalid_arguments", message="match must be an object")
            wait_payload["match"] = {str(key): value for key, value in raw_match.items()}
        raw_timeout_ms = arguments.get("timeout_ms")
        if raw_timeout_ms is not None:
            timeout_ms = cls._normalize_non_negative_number(raw_timeout_ms)
            if timeout_ms is None:
                raise PluginUIBridgeError(
                    code="invalid_arguments",
                    message="timeout_ms must be a non-negative number",
                )
            wait_payload["timeout_ms"] = timeout_ms
        return cls._validate_and_normalize_arguments(
            BridgeOperation.CAPABILITY_INVOKE,
            {
                "plugin_id": arguments.get("plugin_id"),
                "function": "assistant.event.wait",
                "payload": wait_payload,
                "options": arguments.get("options", {}),
                "description": arguments.get("description"),
                "title": arguments.get("title"),
            },
        )

    @classmethod
    def _build_session_wait_for_end_invoke_payload(cls, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_session_id = arguments.get("session_id")
        session_id = str(raw_session_id or "").strip()
        if not session_id:
            raise PluginUIBridgeError(code="invalid_arguments", message="session_id is required")
        wait_payload: Dict[str, Any] = {
            "session_id": session_id,
        }

        raw_timeout_ms = arguments.get("timeout_ms")
        if raw_timeout_ms is not None:
            timeout_ms = cls._normalize_non_negative_number(raw_timeout_ms)
            if timeout_ms is None:
                raise PluginUIBridgeError(
                    code="invalid_arguments",
                    message="timeout_ms must be a non-negative number",
                )
            wait_payload["timeout_ms"] = timeout_ms

        return cls._validate_and_normalize_arguments(
            BridgeOperation.CAPABILITY_INVOKE,
            {
                "plugin_id": arguments.get("plugin_id"),
                "function": "assistant.session.wait_for_end",
                "payload": wait_payload,
                "options": arguments.get("options", {}),
                "description": arguments.get("description"),
                "title": arguments.get("title"),
            },
        )

    @staticmethod
    def _resolve_plugin_id(plugin_id: str) -> str:
        raw_key = str(plugin_id or "").strip()
        if not raw_key:
            raise PluginUIBridgeError(code="missing_plugin_id", message="plugin_id is required")
        try:
            resolved = get_plugin_id_resolver().resolve(raw_key)
        except PluginIdResolveError as err:
            raise PluginUIBridgeError(code=err.code, message=err.message, details=err.details) from err
        return resolved.canonical_plugin_id

    @staticmethod
    def _build_definitions() -> Dict[str, UiToolDefinition]:
        defs = [
            UiToolDefinition(
                name="dawnchat.ui.describe",
                description="Capture UI tree snapshot from plugin preview iframe with selectable scope",
                op=BridgeOperation.DESCRIBE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                        "scope": {
                            "type": "string",
                            "enum": ["all", "visible", "viewport"],
                            "default": "all",
                            "description": (
                                "UI snapshot scope. "
                                "'all' returns DOM nodes without visibility filtering; "
                                "'visible' returns style/layout-visible nodes only; "
                                "'viewport' returns visible nodes fully inside current viewport."
                            ),
                        },
                        "max_nodes": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 500,
                            "description": "Maximum number of nodes returned (1-500).",
                        },
                        "include_screenshot": {"type": "boolean"},
                    },
                    "required": ["plugin_id"],
                },
            ),
            UiToolDefinition(
                name="dawnchat.ui.query",
                description="Query UI nodes by selector or locator hints",
                op=BridgeOperation.QUERY,
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                        "locator": {"type": "object"},
                        "include_screenshot": {"type": "boolean"},
                    },
                    "required": ["plugin_id", "locator"],
                },
            ),
            UiToolDefinition(
                name="dawnchat.ui.act",
                description="Execute UI action (click/type/set_value/focus/press_key)",
                op=BridgeOperation.ACT,
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                        "action": {"type": "string"},
                        "target": {
                            "type": "object",
                            "description": "Canonical target locator. Backward-compatible legacy fields are normalized server-side.",
                            "properties": {
                                "nodeId": {"type": "string"},
                                "pathIndex": {"type": "string"},
                                "selector": {"type": "string"},
                                "index": {"type": "integer", "minimum": 0},
                                "textContains": {"type": "string"},
                                "bounds": {
                                    "type": "object",
                                    "properties": {
                                        "x": {"type": "number"},
                                        "y": {"type": "number"},
                                        "width": {"type": "number"},
                                        "height": {"type": "number"},
                                    },
                                    "required": ["x", "y", "width", "height"],
                                },
                            },
                        },
                        "args": {"type": "object"},
                        "options": {"type": "object"},
                    },
                    "required": ["plugin_id", "action", "target"],
                },
            ),
            UiToolDefinition(
                name="dawnchat.ui.scroll",
                description=(
                    "Scroll viewport or a target container. "
                    "Use y/x for absolute position (pixels), "
                    "or direction (up/down/top/bottom) with optional distance (pixels)."
                ),
                op=BridgeOperation.SCROLL,
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                        "target": {
                            "type": "object",
                            "description": "Optional target scroll container locator.",
                            "properties": {
                                "nodeId": {"type": "string"},
                                "pathIndex": {"type": "string"},
                                "selector": {"type": "string"},
                                "index": {"type": "integer", "minimum": 0},
                                "textContains": {"type": "string"},
                                "bounds": {
                                    "type": "object",
                                    "properties": {
                                        "x": {"type": "number"},
                                        "y": {"type": "number"},
                                        "width": {"type": "number"},
                                        "height": {"type": "number"},
                                    },
                                    "required": ["x", "y", "width", "height"],
                                },
                            },
                        },
                        "y": {
                            "type": "number",
                            "minimum": 0,
                            "description": "Absolute scrollTop in pixels (recommended).",
                        },
                        "x": {
                            "type": "number",
                            "minimum": 0,
                            "description": "Absolute scrollLeft in pixels.",
                        },
                        "direction": {
                            "type": "string",
                            "enum": ["up", "down", "top", "bottom"],
                            "description": "Relative/shortcut scroll mode when y is not provided.",
                        },
                        "distance": {
                            "type": "number",
                            "minimum": 1,
                            "description": "Scroll delta in pixels for up/down.",
                        },
                        "options": {"type": "object"},
                    },
                    "required": ["plugin_id"],
                },
            ),
            UiToolDefinition(
                name="dawnchat.ui.capabilities.list",
                description="List assistant feature scenes and minimal top-level UI entrypoints",
                op=BridgeOperation.CAPABILITIES_LIST,
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                    },
                    "required": ["plugin_id"],
                },
            ),
            UiToolDefinition(
                name="dawnchat.ui.capability.invoke",
                description=(
                    "Invoke a plugin-exposed UI capability with structured payload. "
                    "For function=view.open, use view_id plus optional resource and initial_anchor. "
                    "For function=view.capability.invoke, use view_id + capability_id + input."
                ),
                op=BridgeOperation.CAPABILITY_INVOKE,
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                        "function": {"type": "string"},
                        "payload": {
                            "type": "object",
                            "description": (
                                "Plugin-defined payload object. "
                                "For function=view.open, the standard wrapper is "
                                "{view_id, resource?, initial_anchor?}. "
                                "For function=view.capability.invoke, the standard wrapper is "
                                "{view_id, capability_id, input}."
                            ),
                        },
                        "options": {"type": "object"},
                    },
                    "required": ["plugin_id", "function"],
                },
            ),
            UiToolDefinition(
                name="dawnchat.ui.session.start",
                description="Start a host-managed assistant session with ordered steps",
                op=BridgeOperation.CAPABILITY_INVOKE,
                capability_function="assistant.session.start",
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                        "steps": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "action": {
                                        "type": "object",
                                        "properties": {
                                            "type": {"type": "string"},
                                            "payload": {"type": "object"},
                                        },
                                        "required": ["type"],
                                    },
                                    "timeout_ms": {"type": "number", "minimum": 0, "default": 30000},
                                },
                                "required": ["action"],
                            },
                        },
                        "options": {"type": "object"},
                    },
                    "required": ["plugin_id", "steps"],
                },
            ),
            UiToolDefinition(
                name="dawnchat.ui.session.status",
                description="Get host-managed assistant session status by session_id",
                op=BridgeOperation.CAPABILITY_INVOKE,
                capability_function="assistant.session.status",
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                        "session_id": {"type": "string"},
                        "options": {"type": "object"},
                    },
                    "required": ["plugin_id", "session_id"],
                },
            ),
            UiToolDefinition(
                name="dawnchat.ui.session.stop",
                description="Stop a host-managed assistant session by session_id",
                op=BridgeOperation.CAPABILITY_INVOKE,
                capability_function="assistant.session.stop",
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                        "session_id": {"type": "string"},
                        "reason": {"type": "string"},
                        "options": {"type": "object"},
                    },
                    "required": ["plugin_id", "session_id"],
                },
            ),
            UiToolDefinition(
                name="dawnchat.ui.event.wait",
                description="Wait for runtime event(s) emitted from the plugin preview",
                op=BridgeOperation.CAPABILITY_INVOKE,
                capability_function="assistant.event.wait",
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                        "event_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                        },
                        "match": {"type": "object"},
                        "timeout_ms": {"type": "number", "minimum": 0},
                        "options": {"type": "object"},
                    },
                    "required": ["plugin_id", "event_types"],
                },
            ),
            UiToolDefinition(
                name="dawnchat.ui.session.wait_for_end",
                description="Wait for a host-managed assistant session to reach terminal state",
                op=BridgeOperation.CAPABILITY_INVOKE,
                capability_function="assistant.session.wait_for_end",
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                        "session_id": {"type": "string"},
                        "timeout_ms": {"type": "number", "minimum": 0},
                        "options": {"type": "object"},
                    },
                    "required": ["plugin_id", "session_id"],
                },
            ),
            UiToolDefinition(
                name="dawnchat.ui.runtime.info",
                description="Get plugin runtime/preview status and MCP endpoint diagnostics",
                op=BridgeOperation.RUNTIME_INFO,
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                    },
                    "required": ["plugin_id"],
                },
            ),
            UiToolDefinition(
                name="dawnchat.ui.runtime.refresh",
                description="Soft refresh plugin preview iframe when HMR does not apply",
                op=BridgeOperation.RUNTIME_REFRESH,
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                    },
                    "required": ["plugin_id"],
                },
            ),
            UiToolDefinition(
                name="dawnchat.ui.runtime.restart",
                description="Restart plugin dev session and return lifecycle task id",
                op=BridgeOperation.RUNTIME_RESTART,
                input_schema={
                    "type": "object",
                    "properties": {
                        "plugin_id": {"type": "string"},
                        "target": {
                            "type": "string",
                            "enum": ["dev_session"],
                            "default": "dev_session",
                        },
                    },
                    "required": ["plugin_id"],
                },
            ),
        ]
        for item in defs:
            properties = item.input_schema.setdefault("properties", {})
            if "description" not in properties:
                properties["description"] = {
                    "type": "string",
                    "description": "Short user-facing intent for this call (5-12 words).",
                }
            if "title" not in properties:
                properties["title"] = {
                    "type": "string",
                    "description": "Legacy intent text. Prefer description.",
                }
        return {item.name: item for item in defs}

    @staticmethod
    def _assert_view_capability_invoke_payload_shape(
        payload: Dict[str, Any],
        *,
        context: str,
    ) -> None:
        """Reject common Agent mistake: capability_id / view_id nested inside input."""
        inner = payload.get("input")
        if not isinstance(inner, dict):
            return
        misplaced = [key for key in ("capability_id", "view_id") if key in inner]
        if misplaced:
            raise PluginUIBridgeError(
                code="invalid_arguments",
                message=(
                    f"{context}: use payload shape {{view_id, capability_id, input}} with only "
                    "business fields inside input; do not put view_id or capability_id inside input. "
                    f"Found under input: {', '.join(misplaced)}."
                ),
            )

    @staticmethod
    def _validate_and_normalize_arguments(op: BridgeOperation, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload = {k: v for k, v in arguments.items() if k != "plugin_id"}
        description = UiToolService._normalize_description(
            payload.get("description"),
            payload.get("title"),
        )
        if description:
            payload["description"] = description
        payload.pop("title", None)
        if op == BridgeOperation.DESCRIBE:
            raw_scope = payload.get("scope")
            scope = str(raw_scope or "all").strip().lower()
            if scope not in UiToolService._DESCRIBE_SCOPE_ALLOWED:
                raise PluginUIBridgeError(
                    code="invalid_arguments",
                    message=f"scope must be one of: {', '.join(UiToolService._DESCRIBE_SCOPE_ALLOWED)}",
                )
            payload["scope"] = scope

            max_nodes = payload.get("max_nodes")
            if max_nodes is not None:
                parsed_max_nodes = UiToolService._normalize_index(max_nodes)
                if parsed_max_nodes is None or parsed_max_nodes <= 0:
                    raise PluginUIBridgeError(
                        code="invalid_arguments",
                        message="max_nodes must be an integer between 1 and 500",
                    )
                if parsed_max_nodes > 500:
                    raise PluginUIBridgeError(
                        code="invalid_arguments",
                        message="max_nodes must be an integer between 1 and 500",
                    )
                payload["max_nodes"] = parsed_max_nodes
        if op == BridgeOperation.QUERY:
            locator = payload.get("locator")
            if not isinstance(locator, dict):
                raise PluginUIBridgeError(code="invalid_arguments", message="locator must be an object")
        if op == BridgeOperation.ACT:
            action = str(payload.get("action") or "").strip()
            target = payload.get("target")
            if target is None and isinstance(payload.get("locator"), dict):
                # Be tolerant with clients that still send top-level locator.
                target = {"locator": payload.get("locator")}
            if not action:
                raise PluginUIBridgeError(code="invalid_arguments", message="action is required")
            if action.lower() == "scroll":
                raise PluginUIBridgeError(
                    code="invalid_arguments",
                    message="scroll is provided by dedicated tool dawnchat.ui.scroll",
                )
            target = UiToolService._normalize_act_target(target)
            if not isinstance(target, dict):
                raise PluginUIBridgeError(code="invalid_arguments", message="target must be an object")
            if not UiToolService._has_effective_target(target):
                raise PluginUIBridgeError(
                    code="invalid_arguments",
                    message="target must include at least one locator field",
                    details={"accepted_fields": list(UiToolService._ACT_TARGET_REQUIRED_ANY)},
                )
            payload["target"] = target
        if op == BridgeOperation.SCROLL:
            direction = str(payload.get("direction") or "").strip().lower()
            y = payload.get("y")
            x = payload.get("x")
            distance = payload.get("distance")
            if direction and direction not in {"up", "down", "top", "bottom"}:
                raise PluginUIBridgeError(
                    code="invalid_arguments",
                    message="direction must be one of: up/down/top/bottom",
                )
            if y is not None:
                parsed_y = UiToolService._normalize_non_negative_number(y)
                if parsed_y is None:
                    raise PluginUIBridgeError(code="invalid_arguments", message="y must be a non-negative number")
                payload["y"] = parsed_y
            if x is not None:
                parsed_x = UiToolService._normalize_non_negative_number(x)
                if parsed_x is None:
                    raise PluginUIBridgeError(code="invalid_arguments", message="x must be a non-negative number")
                payload["x"] = parsed_x
            if distance is not None:
                parsed_distance = UiToolService._normalize_positive_number(distance)
                if parsed_distance is None:
                    raise PluginUIBridgeError(
                        code="invalid_arguments",
                        message="distance must be a positive number",
                    )
                payload["distance"] = parsed_distance
            if payload.get("y") is None and not direction:
                raise PluginUIBridgeError(
                    code="invalid_arguments",
                    message="scroll requires y (absolute) or direction",
                )
            if payload.get("y") is not None and direction:
                raise PluginUIBridgeError(
                    code="invalid_arguments",
                    message="y and direction are mutually exclusive",
                )
            target = payload.get("target")
            if target is not None:
                normalized_target = UiToolService._normalize_act_target(target)
                if not isinstance(normalized_target, dict):
                    raise PluginUIBridgeError(code="invalid_arguments", message="target must be an object")
                if not UiToolService._has_effective_target(normalized_target):
                    raise PluginUIBridgeError(
                        code="invalid_arguments",
                        message="target must include at least one locator field",
                        details={"accepted_fields": list(UiToolService._ACT_TARGET_REQUIRED_ANY)},
                    )
                payload["target"] = normalized_target
        if op == BridgeOperation.CAPABILITIES_LIST:
            return {}
        if op == BridgeOperation.RUNTIME_INFO:
            return {}
        if op == BridgeOperation.RUNTIME_REFRESH:
            return {"description": description} if description else {}
        if op == BridgeOperation.RUNTIME_RESTART:
            target = str(payload.get("target") or "dev_session").strip().lower()
            if target != "dev_session":
                raise PluginUIBridgeError(code="invalid_arguments", message="target must be 'dev_session'")
            normalized = {"target": target}
            if description:
                normalized["description"] = description
            return normalized
        if op == BridgeOperation.CAPABILITY_INVOKE:
            function_name = str(payload.get("function") or "").strip()
            if not function_name:
                raise PluginUIBridgeError(code="invalid_arguments", message="function is required")
            options = payload.get("options")
            if options is not None and not isinstance(options, dict):
                raise PluginUIBridgeError(code="invalid_arguments", message="options must be an object")
            raw_payload = payload.get("payload")
            if raw_payload is None:
                normalized_payload: Dict[str, Any] = {}
            elif isinstance(raw_payload, dict):
                normalized_payload = {str(key): value for key, value in raw_payload.items()}
            else:
                raise PluginUIBridgeError(code="invalid_arguments", message="payload must be an object")
            if function_name == "view.capability.invoke":
                UiToolService._assert_view_capability_invoke_payload_shape(
                    normalized_payload,
                    context="dawnchat.ui.capability.invoke(function=view.capability.invoke)",
                )
            normalized_invoke: Dict[str, Any] = {
                "function": function_name,
                "payload": normalized_payload,
                "options": options if isinstance(options, dict) else {},
            }
            if description:
                normalized_invoke["description"] = description
            return normalized_invoke
        return payload

    @staticmethod
    def _build_local_response(
        op: BridgeOperation,
        data: Dict[str, Any],
        elapsed_ms: int,
        display_title: str,
        display_source: str,
    ) -> Dict[str, Any]:
        return {
            "ok": True,
            "data": data,
            "artifacts": [],
            "display": {
                "title": display_title,
                "source": display_source,
            },
            "debug": {
                "request_id": "local",
                "op": op.value,
                "elapsed_ms": elapsed_ms,
            },
        }

    @classmethod
    def _normalize_description(cls, value: Any, legacy_title: Any) -> str:
        raw = value if value is not None else legacy_title
        text = str(raw or "").strip()
        if not text:
            return ""
        if len(text) > cls._DESCRIPTION_MAX_LENGTH:
            raise PluginUIBridgeError(
                code="invalid_arguments",
                message=f"description must be <= {cls._DESCRIPTION_MAX_LENGTH} characters",
            )
        return text

    @classmethod
    def _resolve_display_title(cls, tool: UiToolDefinition, payload: Dict[str, Any]) -> Tuple[str, str]:
        description = str(payload.get("description") or "").strip()
        if description:
            return description, "agent_description"
        return cls._generate_display_title(tool, payload), "server_generated"

    @staticmethod
    def _generate_display_title(tool: UiToolDefinition, payload: Dict[str, Any]) -> str:
        op = tool.op
        if op == BridgeOperation.DESCRIBE:
            scope = str(payload.get("scope") or "all").strip().lower()
            return f"查看界面快照（{scope}）"
        if op == BridgeOperation.QUERY:
            locator = payload.get("locator")
            if isinstance(locator, dict):
                selector = str(locator.get("selector") or "").strip()
                text = str(locator.get("textContains") or locator.get("text_contains") or "").strip()
                if selector:
                    return f"查询界面元素（{selector}）"
                if text:
                    return f"查询界面元素（包含“{text}”）"
            return "查询界面元素"
        if op == BridgeOperation.ACT:
            action = str(payload.get("action") or "").strip().lower()
            if action:
                return f"执行界面操作（{action}）"
            return "执行界面操作"
        if op == BridgeOperation.SCROLL:
            y = payload.get("y")
            direction = str(payload.get("direction") or "").strip().lower()
            if y is not None:
                return "滚动到指定位置"
            if direction:
                return f"滚动界面（{direction}）"
            return "滚动界面"
        if op == BridgeOperation.CAPABILITIES_LIST:
            return "查看可用能力"
        if op == BridgeOperation.CAPABILITY_INVOKE:
            function_name = str(payload.get("function") or "").strip()
            if function_name:
                return f"调用能力（{function_name}）"
            return "调用能力"
        if op == BridgeOperation.RUNTIME_INFO:
            return "查看运行状态"
        if op == BridgeOperation.RUNTIME_REFRESH:
            return "刷新预览页面"
        if op == BridgeOperation.RUNTIME_RESTART:
            return "重启插件开发会话"
        return tool.name

    async def _build_capabilities_catalog(self, plugin_id: str) -> Dict[str, Any]:
        list_payload = {
            "function": "assistant.view.list",
            "payload": {},
            "options": {},
        }
        list_result = await self._bridge.dispatch(
            plugin_id=plugin_id,
            op=BridgeOperation.CAPABILITY_INVOKE,
            payload=list_payload,
        )
        raw_result = list_result.result
        if not isinstance(raw_result, dict) or raw_result.get("ok") is False:
            raise PluginUIBridgeError(
                code="capabilities_catalog_unavailable",
                message="assistant.view.list did not return a usable capability catalog",
            )
        data = raw_result.get("data")
        if not isinstance(data, dict):
            raise PluginUIBridgeError(
                code="capabilities_catalog_invalid",
                message="assistant.view.list returned invalid data",
            )
        return data

    @staticmethod
    def _normalize_act_target(target: Any) -> Dict[str, Any] | None:
        source = target
        if isinstance(source, str):
            parsed = UiToolService._parse_target_json(source)
            if parsed is None:
                return None
            source = parsed
        if not isinstance(source, dict):
            return None

        locator = source.get("locator")
        locator_obj = locator if isinstance(locator, dict) else {}

        normalized: Dict[str, Any] = {}
        node_id = UiToolService._pick_value(source, locator_obj, ["nodeId", "node_id"])
        if isinstance(node_id, str) and node_id.strip():
            normalized["nodeId"] = node_id.strip()

        path_index = UiToolService._pick_value(source, locator_obj, ["pathIndex", "path_index"])
        if isinstance(path_index, str) and path_index.strip():
            normalized["pathIndex"] = path_index.strip()

        selector = UiToolService._pick_value(source, locator_obj, ["selector"])
        if isinstance(selector, str) and selector.strip():
            normalized["selector"] = selector.strip()

        text_contains = UiToolService._pick_value(source, locator_obj, ["textContains", "text_contains"])
        if isinstance(text_contains, str) and text_contains.strip():
            normalized["textContains"] = text_contains.strip()

        index = UiToolService._pick_value(source, locator_obj, ["index"])
        parsed_index = UiToolService._normalize_index(index)
        if parsed_index is not None:
            normalized["index"] = parsed_index

        bounds = UiToolService._pick_value(source, locator_obj, ["bounds"])
        if isinstance(bounds, dict):
            normalized_bounds = UiToolService._normalize_bounds(bounds)
            if normalized_bounds:
                normalized["bounds"] = normalized_bounds

        return normalized

    @staticmethod
    def _parse_target_json(raw_target: str) -> Dict[str, Any] | None:
        try:
            decoded = json.loads(raw_target)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None

    @staticmethod
    def _pick_value(primary: Dict[str, Any], secondary: Dict[str, Any], keys: List[str]) -> Any:
        for key in keys:
            value = primary.get(key)
            if value is not None:
                return value
        for key in keys:
            value = secondary.get(key)
            if value is not None:
                return value
        return None

    @staticmethod
    def _normalize_bounds(bounds: Dict[str, Any]) -> Dict[str, int] | None:
        keys = ("x", "y", "width", "height")
        normalized: Dict[str, int] = {}
        for key in keys:
            value = bounds.get(key)
            if not isinstance(value, (int, float)):
                return None
            normalized[key] = int(value)
        if normalized["width"] <= 0 or normalized["height"] <= 0:
            return None
        return normalized

    @staticmethod
    def _normalize_index(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value if value >= 0 else None
        if isinstance(value, float):
            parsed = int(value)
            return parsed if parsed >= 0 else None
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            if raw.isdigit():
                return int(raw)
        return None

    @staticmethod
    def _normalize_non_negative_number(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            parsed = float(value)
            return parsed if parsed >= 0 else None
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            try:
                parsed = float(raw)
            except ValueError:
                return None
            return parsed if parsed >= 0 else None
        return None

    @staticmethod
    def _normalize_positive_number(value: Any) -> float | None:
        parsed = UiToolService._normalize_non_negative_number(value)
        if parsed is None or parsed <= 0:
            return None
        return parsed

    @classmethod
    def _has_effective_target(cls, target: Dict[str, Any]) -> bool:
        for key in cls._ACT_TARGET_REQUIRED_ANY:
            value = target.get(key)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            return True
        return False

    @staticmethod
    def _compact_data(op: BridgeOperation, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = payload.get("data")
        if not isinstance(data, dict):
            return payload
        rows = data.get("nodes")
        if op in {BridgeOperation.DESCRIBE, BridgeOperation.QUERY} and isinstance(rows, list):
            head = rows[:40]
            cloned = dict(payload)
            compact_data = dict(data)
            compact_data["nodes"] = head
            compact_data["node_count"] = len(rows)
            compact_data["nodes_truncated"] = len(rows) > len(head)
            cloned["data"] = compact_data
            return cloned
        return payload


_ui_tool_service: UiToolService | None = None


def get_ui_tool_service() -> UiToolService:
    global _ui_tool_service
    if _ui_tool_service is None:
        _ui_tool_service = UiToolService()
    return _ui_tool_service
