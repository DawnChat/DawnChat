import pytest

from app.plugin_ui_bridge.errors import PluginUIBridgeError
from app.voice.voice_mcp_service import VoiceMcpService
import app.services.plugin_id_resolver as resolver_module


class _RuntimeStub:
    def __init__(self) -> None:
        self.last_submit_kwargs = {}
        self.last_stop_kwargs = {}
        self.bridge_records = []

    async def submit_speak(self, **kwargs):
        self.last_submit_kwargs = kwargs
        return "task-1"

    async def stop(self, **kwargs):
        self.last_stop_kwargs = kwargs
        return True

    def get_task(self, task_id: str):
        if task_id == "task-1":
            return {"task_id": "task-1", "plugin_id": "com.demo", "status": "completed"}
        return None

    def get_plugin_runtime_state(self, plugin_id: str):
        return {"state": "available", "plugin_id": plugin_id}

    async def record_bridge_notify(self, *, plugin_id: str, ok: bool, error_code: str = ""):
        self.bridge_records.append((plugin_id, ok, error_code))


class _BridgeStub:
    def __init__(self, *, should_fail: bool = False, alias_map: dict[str, str] | None = None) -> None:
        self.should_fail = should_fail
        self.alias_map = alias_map or {}
        self.events = []

    async def resolve_connected_plugin_id(self, plugin_id: str) -> str:
        return self.alias_map.get(plugin_id, plugin_id)

    async def push_event(self, plugin_id: str, event, payload):
        if self.should_fail:
            raise PluginUIBridgeError(code="bridge_not_connected", message="bridge not connected")
        self.events.append((plugin_id, event.value, payload))


class _PluginManagerStub:
    def __init__(self) -> None:
        self._plugin_id = "com.demo.plugin"

    def get_plugin_snapshot(self, plugin_id: str):
        if plugin_id == self._plugin_id:
            return {"id": plugin_id}
        return None

    def list_plugins(self):
        return [{"id": self._plugin_id}]


@pytest.mark.asyncio
async def test_speak_returns_task_id() -> None:
    runtime = _RuntimeStub()
    bridge = _BridgeStub()
    service = VoiceMcpService(runtime_service=runtime, bridge_service=bridge)
    payload = await service.execute("dawnchat.voice.speak", {"plugin_id": "com.demo", "text": "hello", "sid": 6})
    assert payload["ok"] is True
    assert payload["data"]["task_id"] == "task-1"
    assert runtime.last_submit_kwargs["sid"] == 6
    assert bridge.events[0][0] == "com.demo"
    assert bridge.events[0][1] == "tts_speak_accepted"
    assert bridge.events[0][2]["task_id"] == "task-1"
    assert runtime.bridge_records[-1] == ("com.demo", True, "")


@pytest.mark.asyncio
async def test_status_by_task() -> None:
    service = VoiceMcpService(runtime_service=_RuntimeStub())
    payload = await service.execute("dawnchat.voice.status", {"task_id": "task-1"})
    assert payload["ok"] is True
    assert payload["data"]["task"]["status"] == "completed"


@pytest.mark.asyncio
async def test_invalid_sid_returns_invalid_arguments() -> None:
    service = VoiceMcpService(runtime_service=_RuntimeStub())
    payload = await service.execute("dawnchat.voice.speak", {"plugin_id": "com.demo", "text": "hello", "sid": -1})
    assert payload["ok"] is False
    assert payload["error_code"] == "invalid_arguments"


@pytest.mark.asyncio
async def test_stop_pushes_bridge_event_with_plugin_from_task() -> None:
    runtime = _RuntimeStub()
    bridge = _BridgeStub()
    service = VoiceMcpService(runtime_service=runtime, bridge_service=bridge)
    payload = await service.execute("dawnchat.voice.stop", {"task_id": "task-1"})
    assert payload["ok"] is True
    assert payload["data"]["stopped"] is True
    assert runtime.last_stop_kwargs["task_id"] == "task-1"
    assert bridge.events[0][0] == "com.demo"
    assert bridge.events[0][1] == "tts_stopped"
    assert bridge.events[0][2]["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_speak_keeps_success_when_bridge_not_connected() -> None:
    runtime = _RuntimeStub()
    bridge = _BridgeStub(should_fail=True)
    service = VoiceMcpService(runtime_service=runtime, bridge_service=bridge)
    payload = await service.execute("dawnchat.voice.speak", {"plugin_id": "com.demo", "text": "hello"})
    assert payload["ok"] is True
    assert payload["data"]["task_id"] == "task-1"
    assert runtime.bridge_records[-1] == ("com.demo", False, "bridge_not_connected")


@pytest.mark.asyncio
async def test_speak_resolves_safe_plugin_id_alias() -> None:
    runtime = _RuntimeStub()
    bridge = _BridgeStub(alias_map={"com.demo_plugin": "com.demo.plugin"})
    service = VoiceMcpService(runtime_service=runtime, bridge_service=bridge)
    payload = await service.execute("dawnchat.voice.speak", {"plugin_id": "com.demo_plugin", "text": "hello"})
    assert payload["ok"] is True
    assert runtime.last_submit_kwargs["plugin_id"] == "com.demo.plugin"
    assert bridge.events[0][0] == "com.demo.plugin"


@pytest.mark.asyncio
async def test_speak_resolves_safe_plugin_id_via_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = _RuntimeStub()
    bridge = _BridgeStub()
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: _PluginManagerStub())
    service = VoiceMcpService(runtime_service=runtime, bridge_service=bridge)

    payload = await service.execute("dawnchat.voice.speak", {"plugin_id": "com_demo_plugin", "text": "hello"})

    assert payload["ok"] is True
    assert runtime.last_submit_kwargs["plugin_id"] == "com.demo.plugin"
    assert bridge.events[0][0] == "com.demo.plugin"
