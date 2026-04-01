from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.plugin_ui_bridge.errors import PluginUIBridgeError
from app.plugin_ui_bridge.models import BridgeOperation
from app.plugin_ui_bridge.service import BridgeDispatchResult
from app.plugin_ui_bridge.ui_tool_service import UiToolService
import app.plugin_ui_bridge.ui_tool_service as ui_tool_service_module
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
async def test_session_wait_dispatches_as_capability_invoke(monkeypatch: pytest.MonkeyPatch) -> None:
    bridge = _BridgeStub()
    service = UiToolService(bridge_service=bridge, artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    result = await service.execute(
        "dawnchat.ui.session.wait",
        {
            "plugin_id": "com.demo.plugin",
            "session_id": "sess_1",
            "wait_for": "runtime_event",
            "event_types": ["assistant.guide.quiz.submitted"],
            "match": {"quiz_id": "quiz-1"},
            "since_seq": 3,
            "timeout_ms": 15000,
        },
    )

    assert result["ok"] is True
    assert bridge.last_op == BridgeOperation.CAPABILITY_INVOKE
    assert bridge.last_payload["function"] == "assistant.session.wait"
    assert bridge.last_payload["payload"] == {
        "session_id": "sess_1",
        "wait_for": "runtime_event",
        "event_types": ["assistant.guide.quiz.submitted"],
        "match": {"quiz_id": "quiz-1"},
        "since_seq": 3,
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
async def test_session_wait_requires_event_types_for_runtime_event(monkeypatch: pytest.MonkeyPatch) -> None:
    service = UiToolService(bridge_service=_BridgeStub(), artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    with pytest.raises(PluginUIBridgeError) as exc:
        await service.execute(
            "dawnchat.ui.session.wait",
            {
                "plugin_id": "com.demo.plugin",
                "session_id": "sess_1",
                "wait_for": "runtime_event",
            },
        )
    assert exc.value.code == "invalid_arguments"
    assert exc.value.message == "event_types is required when wait_for=runtime_event"


@pytest.mark.asyncio
async def test_session_wait_requires_session_id(monkeypatch: pytest.MonkeyPatch) -> None:
    service = UiToolService(bridge_service=_BridgeStub(), artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _ManagerStub())

    with pytest.raises(PluginUIBridgeError) as exc:
        await service.execute(
            "dawnchat.ui.session.wait",
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
