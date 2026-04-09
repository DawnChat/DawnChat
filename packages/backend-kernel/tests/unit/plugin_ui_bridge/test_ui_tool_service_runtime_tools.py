from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.plugin_ui_bridge.errors import PluginUIBridgeError
from app.plugin_ui_bridge.models import BridgeOperation
from app.plugin_ui_bridge.service import BridgeDispatchResult
import app.plugin_ui_bridge.ui_tool_service as ui_tool_service_module
from app.plugin_ui_bridge.ui_tool_service import UiToolService
import app.services.plugin_id_resolver as resolver_module


class _BridgeStub:
    def __init__(self) -> None:
        self.last_op: BridgeOperation | None = None
        self.last_plugin_id: str = ""
        self.last_payload: dict = {}

    async def dispatch(self, plugin_id: str, op: BridgeOperation, payload: dict) -> BridgeDispatchResult:
        self.last_op = op
        self.last_plugin_id = plugin_id
        self.last_payload = payload
        return BridgeDispatchResult(
            request_id="req_test",
            op=op,
            result={"ok": True, "data": {"accepted": True}},
        )


class _CapabilitiesCatalogBridgeStub(_BridgeStub):
    async def dispatch(self, plugin_id: str, op: BridgeOperation, payload: dict) -> BridgeDispatchResult:
        self.last_op = op
        self.last_plugin_id = plugin_id
        self.last_payload = payload
        if op == BridgeOperation.CAPABILITY_INVOKE and payload.get("function") == "assistant.view.list":
            return BridgeDispatchResult(
                request_id="req_catalog",
                op=op,
                result={
                    "ok": True,
                    "data": {
                        "active_view_id": "tictactoe.main",
                        "views": [
                            {
                                "view_id": "word.main",
                                "title": "Word Workspace",
                                "resource_type": "word",
                                "state_mode": "stateful",
                                "description": "Best for single-resource reading.",
                                "is_active": False,
                                "capabilities": [
                                    {
                                        "capability_id": "append_etymology",
                                        "mode": "write",
                                        "title": "Append Etymology",
                                        "input_schema": {
                                            "type": "object",
                                            "properties": {
                                                "items": {
                                                    "type": "array",
                                                    "items": {"type": "string"},
                                                }
                                            },
                                        },
                                    }
                                ],
                                "capability_invoke_contract": {
                                    "action_type": "view.capability.invoke",
                                    "payload_example": {
                                        "view_id": "word.main",
                                        "capability_id": "<capability_id>",
                                        "input": {},
                                    },
                                    "note": (
                                        "Use capabilities[].capability_id as the identifier and place "
                                        "business parameters inside payload.input."
                                    ),
                                },
                                "view_open_contract": {
                                    "function": "view.open",
                                    "payload_example": {
                                        "view_id": "word.main",
                                        "resource": {},
                                        "initial_anchor": "<anchor_id>",
                                    },
                                    "note": (
                                        "Use this top-level capability to enter a scene and optionally bind "
                                        "resource or initial anchor state."
                                    ),
                                },
                                "recommended_flow": [
                                    "Use the top-level view.open capability with view_id=word.main to bind the target word resource."
                                ],
                            },
                            {
                                "view_id": "tictactoe.main",
                                "title": "TicTacToe Arena",
                                "resource_type": "tictactoe.game",
                                "state_mode": "stateful",
                                "description": "Best for validating realtime board interaction.",
                                "is_active": True,
                                "capabilities": [
                                    {
                                        "capability_id": "game.place_mark",
                                        "mode": "write",
                                        "title": "Place Mark",
                                        "input_schema": {
                                            "type": "object",
                                            "properties": {
                                                "index": {"type": "integer"},
                                            },
                                        },
                                    }
                                ],
                                "capability_invoke_contract": {
                                    "action_type": "view.capability.invoke",
                                    "payload_example": {
                                        "view_id": "tictactoe.main",
                                        "capability_id": "<capability_id>",
                                        "input": {},
                                    },
                                    "note": (
                                        "Use capabilities[].capability_id as the identifier and place "
                                        "business parameters inside payload.input."
                                    ),
                                },
                                "view_open_contract": {
                                    "function": "view.open",
                                    "payload_example": {
                                        "view_id": "tictactoe.main",
                                        "resource": {},
                                        "initial_anchor": "<anchor_id>",
                                    },
                                    "note": (
                                        "Use this top-level capability to enter a scene and optionally bind "
                                        "resource or initial anchor state."
                                    ),
                                },
                                "recommended_flow": [
                                    "Use the top-level view.open capability with view_id=tictactoe.main to bind the round resource."
                                ],
                                "current_state_summary": {
                                    "status": "playing",
                                    "current_player": "X",
                                    "move_count": 2,
                                },
                            },
                        ],
                        "functions": [
                            {
                                "name": "view.open",
                                "description": "Open one registered assistant view and optionally bind its resource payload.",
                                "input_schema": {
                                    "type": "object",
                                    "properties": {
                                        "view_id": {"type": "string"},
                                        "resource": {"type": "object"},
                                        "initial_anchor": {"type": "string"},
                                    },
                                    "required": ["view_id"],
                                },
                            },
                            {
                                "name": "assistant.view.describe",
                                "description": "Inspect one specific view contract or the current active view state.",
                                "input_schema": {
                                    "type": "object",
                                    "properties": {
                                        "view_id": {"type": "string"},
                                    },
                                },
                            }
                        ],
                    },
                },
            )
        return await super().dispatch(plugin_id=plugin_id, op=op, payload=payload)


@dataclass
class _ArtifactResult:
    data: dict
    artifacts: list


class _ArtifactStoreStub:
    def write_result(self, plugin_id: str, request_id: str, op: BridgeOperation, result: dict) -> _ArtifactResult:
        return _ArtifactResult(data=result, artifacts=[])


class _ManagerStub:
    def __init__(self) -> None:
        self._plugin_id = "com.demo.plugin"

    def get_plugin_runtime_info(self, plugin_id: str):
        if plugin_id != self._plugin_id:
            return None
        return {"plugin_id": plugin_id, "preview": {"state": "running"}}

    def get_plugin_snapshot(self, plugin_id: str):
        if plugin_id == self._plugin_id:
            return {"id": plugin_id}
        return None

    def list_plugins(self):
        return [{"id": self._plugin_id}]


class _LifecycleStub:
    async def submit_restart_dev_session(self, plugin_id: str) -> str:
        return "task_demo_1"


@pytest.mark.asyncio
async def test_runtime_info_returns_local_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    manager = _ManagerStub()
    monkeypatch.setattr(ui_tool_service_module, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: manager)

    result = await service.execute("dawnchat.ui.runtime.info", {"plugin_id": "com.demo.plugin"})

    assert result["ok"] is True
    assert result["data"]["plugin_id"] == "com.demo.plugin"
    assert result["debug"]["op"] == "runtime_info"
    assert bridge.last_op is None


@pytest.mark.asyncio
async def test_runtime_restart_returns_task_id(monkeypatch: pytest.MonkeyPatch) -> None:
    service = UiToolService(bridge_service=_BridgeStub(), artifact_store=_ArtifactStoreStub())
    manager = _ManagerStub()
    monkeypatch.setattr(ui_tool_service_module, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(ui_tool_service_module, "get_plugin_lifecycle_service", lambda: _LifecycleStub())
    monkeypatch.setattr(ui_tool_service_module.Config, "API_PORT", 18080)

    result = await service.execute("dawnchat.ui.runtime.restart", {"plugin_id": "com.demo.plugin"})

    assert result["ok"] is True
    assert result["data"]["task_id"] == "task_demo_1"
    assert result["data"]["target"] == "dev_session"
    assert result["data"]["poll_url"].endswith("/api/plugins/operations/task_demo_1")


@pytest.mark.asyncio
async def test_runtime_refresh_dispatches_bridge_operation(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute("dawnchat.ui.runtime.refresh", {"plugin_id": "com.demo.plugin"})

    assert result["ok"] is True
    assert bridge.last_op == BridgeOperation.RUNTIME_REFRESH
    assert result["display"]["title"] == "刷新预览页面"
    assert result["display"]["source"] == "server_generated"


@pytest.mark.asyncio
async def test_runtime_info_resolves_safe_name_plugin_id(monkeypatch: pytest.MonkeyPatch) -> None:
    service = UiToolService(bridge_service=_BridgeStub(), artifact_store=_ArtifactStoreStub())
    manager = _ManagerStub()
    monkeypatch.setattr(ui_tool_service_module, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: manager)

    result = await service.execute("dawnchat.ui.runtime.info", {"plugin_id": "com_demo_plugin"})

    assert result["ok"] is True
    assert result["data"]["plugin_id"] == "com.demo.plugin"


@pytest.mark.asyncio
async def test_runtime_refresh_dispatches_with_canonical_plugin_id(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute("dawnchat.ui.runtime.refresh", {"plugin_id": "com_demo_plugin"})

    assert result["ok"] is True
    assert bridge.last_plugin_id == "com.demo.plugin"


@pytest.mark.asyncio
async def test_capabilities_list_returns_view_catalog_from_view_list(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _CapabilitiesCatalogBridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute(
        "dawnchat.ui.capabilities.list",
        {
            "plugin_id": "com.demo.plugin",
        },
    )

    assert result["ok"] is True
    assert bridge.last_op == BridgeOperation.CAPABILITY_INVOKE
    assert bridge.last_payload["function"] == "assistant.view.list"
    assert result["data"] == {
        "views": [
            {
                "view_id": "word.main",
                "title": "Word Workspace",
                "resource_type": "word",
                "state_mode": "stateful",
                "description": "Best for single-resource reading.",
                "is_active": False,
                "capabilities": [
                    {
                        "capability_id": "append_etymology",
                        "mode": "write",
                        "title": "Append Etymology",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "items": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                }
                            },
                        },
                    }
                ],
                "capability_invoke_contract": {
                    "action_type": "view.capability.invoke",
                    "payload_example": {
                        "view_id": "word.main",
                        "capability_id": "<capability_id>",
                        "input": {},
                    },
                    "note": (
                        "Use capabilities[].capability_id as the identifier and place "
                        "business parameters inside payload.input."
                    ),
                },
                "view_open_contract": {
                    "function": "view.open",
                    "payload_example": {
                        "view_id": "word.main",
                        "resource": {},
                        "initial_anchor": "<anchor_id>",
                    },
                    "note": (
                        "Use this top-level capability to enter a scene and optionally bind "
                        "resource or initial anchor state."
                    ),
                },
                "recommended_flow": [
                    "Use the top-level view.open capability with view_id=word.main to bind the target word resource."
                ],
            },
            {
                "view_id": "tictactoe.main",
                "title": "TicTacToe Arena",
                "resource_type": "tictactoe.game",
                "state_mode": "stateful",
                "description": "Best for validating realtime board interaction.",
                "is_active": True,
                "capabilities": [
                    {
                        "capability_id": "game.place_mark",
                        "mode": "write",
                        "title": "Place Mark",
                        "input_schema": {
                            "type": "object",
                            "properties": {
                                "index": {"type": "integer"},
                            },
                        },
                    }
                ],
                "capability_invoke_contract": {
                    "action_type": "view.capability.invoke",
                    "payload_example": {
                        "view_id": "tictactoe.main",
                        "capability_id": "<capability_id>",
                        "input": {},
                    },
                    "note": (
                        "Use capabilities[].capability_id as the identifier and place "
                        "business parameters inside payload.input."
                    ),
                },
                "view_open_contract": {
                    "function": "view.open",
                    "payload_example": {
                        "view_id": "tictactoe.main",
                        "resource": {},
                        "initial_anchor": "<anchor_id>",
                    },
                    "note": (
                        "Use this top-level capability to enter a scene and optionally bind "
                        "resource or initial anchor state."
                    ),
                },
                "recommended_flow": [
                    "Use the top-level view.open capability with view_id=tictactoe.main to bind the round resource."
                ],
                "current_state_summary": {
                    "status": "playing",
                    "current_player": "X",
                    "move_count": 2,
                },
            },
        ],
        "functions": [
            {
                "name": "view.open",
                "description": "Open one registered assistant view and optionally bind its resource payload.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "view_id": {"type": "string"},
                        "resource": {"type": "object"},
                        "initial_anchor": {"type": "string"},
                    },
                    "required": ["view_id"],
                },
            },
            {
                "name": "assistant.view.describe",
                "description": "Inspect one specific view contract or the current active view state.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "view_id": {"type": "string"},
                    },
                },
            }
        ],
        "active_view_id": "tictactoe.main",
    }


@pytest.mark.asyncio
async def test_session_start_dispatches_as_capability_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute(
        "dawnchat.ui.session.start",
        {
            "plugin_id": "com.demo.plugin",
            "steps": [
                {
                    "id": "step-1",
                    "action": {
                        "type": "card.show",
                        "payload": {
                            "card_type": "word",
                            "data": {"word": "sync"},
                        },
                    },
                    "timeout_ms": 45000,
                }
            ],
        },
    )

    assert result["ok"] is True
    assert bridge.last_op == BridgeOperation.CAPABILITY_INVOKE
    assert bridge.last_payload["function"] == "assistant.session.start"
    assert bridge.last_payload["payload"]["steps"][0]["action"]["type"] == "card.show"
    assert bridge.last_payload["payload"]["steps"][0]["timeout_ms"] == 45000


@pytest.mark.asyncio
async def test_session_start_preserves_description_for_display_title(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute(
        "dawnchat.ui.session.start",
        {
            "plugin_id": "com.demo.plugin",
            "description": "Starting a guided geometry proof session in Coordinate Lab.",
            "steps": [
                {
                    "id": "setup-viewport",
                    "action": {
                        "type": "view.capability.invoke",
                        "payload": {},
                    },
                }
            ],
        },
    )

    assert result["ok"] is True
    assert bridge.last_payload["function"] == "assistant.session.start"
    assert bridge.last_payload["description"] == "Starting a guided geometry proof session in Coordinate Lab."
    assert result["display"]["title"] == "Starting a guided geometry proof session in Coordinate Lab."
    assert result["display"]["source"] == "agent_description"


@pytest.mark.asyncio
async def test_capability_invoke_preserves_view_capability_id_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute(
        "dawnchat.ui.capability.invoke",
        {
            "plugin_id": "com.demo.plugin",
            "function": "view.capability.invoke",
            "payload": {
                "view_id": "word.main",
                "capability_id": "append_etymology",
                "input": {
                    "items": ["ize"],
                },
            },
        },
    )

    assert result["ok"] is True
    assert bridge.last_op == BridgeOperation.CAPABILITY_INVOKE
    assert bridge.last_payload == {
        "function": "view.capability.invoke",
        "payload": {
            "view_id": "word.main",
            "capability_id": "append_etymology",
            "input": {
                "items": ["ize"],
            },
        },
        "options": {},
    }


@pytest.mark.asyncio
async def test_capability_invoke_preserves_top_level_view_open_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute(
        "dawnchat.ui.capability.invoke",
        {
            "plugin_id": "com.demo.plugin",
            "function": "view.open",
            "payload": {
                "view_id": "board.main",
                "resource": {
                    "resource_type": "board.workspace",
                },
                "initial_anchor": "board.canvas",
            },
        },
    )

    assert result["ok"] is True
    assert bridge.last_op == BridgeOperation.CAPABILITY_INVOKE
    assert bridge.last_payload == {
        "function": "view.open",
        "payload": {
            "view_id": "board.main",
            "resource": {
                "resource_type": "board.workspace",
            },
            "initial_anchor": "board.canvas",
        },
        "options": {},
    }


@pytest.mark.asyncio
async def test_session_status_dispatches_as_capability_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute(
        "dawnchat.ui.session.status",
        {
            "plugin_id": "com.demo.plugin",
            "session_id": "sess_1",
        },
    )

    assert result["ok"] is True
    assert bridge.last_op == BridgeOperation.CAPABILITY_INVOKE
    assert bridge.last_payload["function"] == "assistant.session.status"
    assert bridge.last_payload["payload"]["session_id"] == "sess_1"


@pytest.mark.asyncio
async def test_session_stop_dispatches_as_capability_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute(
        "dawnchat.ui.session.stop",
        {
            "plugin_id": "com.demo.plugin",
            "session_id": "sess_1",
            "reason": "stopped_by_agent",
        },
    )

    assert result["ok"] is True
    assert bridge.last_op == BridgeOperation.CAPABILITY_INVOKE
    assert bridge.last_payload["function"] == "assistant.session.stop"
    assert bridge.last_payload["payload"]["session_id"] == "sess_1"
    assert bridge.last_payload["payload"]["reason"] == "stopped_by_agent"


@pytest.mark.asyncio
async def test_event_wait_dispatches_as_capability_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute(
        "dawnchat.ui.event.wait",
        {
            "plugin_id": "com.demo.plugin",
            "event_types": ["assistant.guide.quiz.submitted"],
            "match": {"quiz_id": "quiz-1"},
            "timeout_ms": 15000,
        },
    )

    assert result["ok"] is True
    assert bridge.last_op == BridgeOperation.CAPABILITY_INVOKE
    assert bridge.last_payload["function"] == "assistant.event.wait"
    assert bridge.last_payload["payload"] == {
        "event_types": ["assistant.guide.quiz.submitted"],
        "match": {"quiz_id": "quiz-1"},
        "timeout_ms": 15000.0,
    }


@pytest.mark.asyncio
async def test_session_wait_for_end_dispatches_as_capability_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute(
        "dawnchat.ui.session.wait_for_end",
        {
            "plugin_id": "com.demo.plugin",
            "session_id": "sess_1",
            "timeout_ms": 15000,
        },
    )

    assert result["ok"] is True
    assert bridge.last_op == BridgeOperation.CAPABILITY_INVOKE
    assert bridge.last_payload["function"] == "assistant.session.wait_for_end"
    assert bridge.last_payload["payload"] == {
        "session_id": "sess_1",
        "timeout_ms": 15000.0,
    }


@pytest.mark.asyncio
async def test_session_start_rejects_invalid_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    service = UiToolService(bridge_service=_BridgeStub(), artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    with pytest.raises(PluginUIBridgeError) as exc:
        await service.execute(
            "dawnchat.ui.session.start",
            {
                "plugin_id": "com.demo.plugin",
                "steps": [],
            },
        )
    assert exc.value.code == "invalid_arguments"
    assert exc.value.message == "steps must be a non-empty array"


@pytest.mark.asyncio
async def test_session_start_normalizes_action_payload_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute(
        "dawnchat.ui.session.start",
        {
            "plugin_id": "com.demo.plugin",
            "steps": [
                {
                    "action": {
                        "type": "card.show",
                    },
                    "timeout_ms": "30000",
                }
            ],
        },
    )

    assert result["ok"] is True
    assert bridge.last_payload["payload"]["steps"][0]["action"]["payload"] == {}
    assert bridge.last_payload["payload"]["steps"][0]["timeout_ms"] == 30000.0


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_session_status_requires_session_id(monkeypatch: pytest.MonkeyPatch) -> None:
    service = UiToolService(bridge_service=_BridgeStub(), artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    with pytest.raises(PluginUIBridgeError) as exc:
        await service.execute(
            "dawnchat.ui.session.status",
            {
                "plugin_id": "com.demo.plugin",
                "session_id": "",
            },
        )
    assert exc.value.code == "invalid_arguments"
    assert exc.value.message == "session_id is required"


@pytest.mark.asyncio
async def test_event_wait_requires_event_types(monkeypatch: pytest.MonkeyPatch) -> None:
    service = UiToolService(bridge_service=_BridgeStub(), artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    with pytest.raises(PluginUIBridgeError) as exc:
        await service.execute(
            "dawnchat.ui.event.wait",
            {
                "plugin_id": "com.demo.plugin",
                "event_types": [],
            },
        )
    assert exc.value.code == "invalid_arguments"
    assert exc.value.message == "event_types must be a non-empty array"


@pytest.mark.asyncio
async def test_event_wait_requires_object_match(monkeypatch: pytest.MonkeyPatch) -> None:
    service = UiToolService(bridge_service=_BridgeStub(), artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    with pytest.raises(PluginUIBridgeError) as exc:
        await service.execute(
            "dawnchat.ui.event.wait",
            {
                "plugin_id": "com.demo.plugin",
                "event_types": ["assistant.guide.quiz.submitted"],
                "match": "invalid",
            },
        )
    assert exc.value.code == "invalid_arguments"
    assert exc.value.message == "match must be an object"


@pytest.mark.asyncio
async def test_session_wait_for_end_requires_session_id(monkeypatch: pytest.MonkeyPatch) -> None:
    service = UiToolService(bridge_service=_BridgeStub(), artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    with pytest.raises(PluginUIBridgeError) as exc:
        await service.execute(
            "dawnchat.ui.session.wait_for_end",
            {
                "plugin_id": "com.demo.plugin",
                "session_id": "",
            },
        )
    assert exc.value.code == "invalid_arguments"
    assert exc.value.message == "session_id is required"


@pytest.mark.asyncio
async def test_session_stop_requires_session_id(monkeypatch: pytest.MonkeyPatch) -> None:
    service = UiToolService(bridge_service=_BridgeStub(), artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    with pytest.raises(PluginUIBridgeError) as exc:
        await service.execute(
            "dawnchat.ui.session.stop",
            {
                "plugin_id": "com.demo.plugin",
                "session_id": " ",
            },
        )
    assert exc.value.code == "invalid_arguments"
    assert exc.value.message == "session_id is required"


def test_tool_definitions_expose_description_field() -> None:
    service = UiToolService(bridge_service=_BridgeStub(), artifact_store=_ArtifactStoreStub())
    defs = {item.name: item for item in service.tool_definitions()}
    describe_schema = defs["dawnchat.ui.describe"].input_schema
    assert "description" in describe_schema["properties"]
    assert "title" in describe_schema["properties"]


@pytest.mark.asyncio
async def test_runtime_refresh_uses_description_as_display_title(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute(
        "dawnchat.ui.runtime.refresh",
        {
            "plugin_id": "com.demo.plugin",
            "description": "刷新插件预览并确认页面状态",
        },
    )

    assert result["ok"] is True
    assert result["display"]["title"] == "刷新插件预览并确认页面状态"
    assert result["display"]["source"] == "agent_description"


@pytest.mark.asyncio
async def test_capability_invoke_accepts_legacy_title_and_maps_to_description(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute(
        "dawnchat.ui.capability.invoke",
        {
            "plugin_id": "com.demo.plugin",
            "function": "view.open",
            "title": "打开目标视图并检查初始状态",
            "payload": {"view_id": "board.main"},
        },
    )

    assert result["ok"] is True
    assert bridge.last_payload["description"] == "打开目标视图并检查初始状态"
    assert result["display"]["title"] == "打开目标视图并检查初始状态"
