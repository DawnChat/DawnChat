import pytest

from app.plugins.manager import PluginManager


class _RuntimeServiceDouble:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def start_plugin(self, plugin_id: str):
        self.calls.append(("start_plugin", (plugin_id,), {}))
        return 9527

    async def stop_plugin(self, plugin_id: str):
        self.calls.append(("stop_plugin", (plugin_id,), {}))
        return True

    async def restart_plugin(self, plugin_id: str):
        self.calls.append(("restart_plugin", (plugin_id,), {}))
        return 9528

    async def wait_for_ready(self, plugin_id: str, process, timeout: float = 30.0, *, session_id: str):
        self.calls.append(("wait_for_ready", (plugin_id, process, timeout), {"session_id": session_id}))
        return True

    async def monitor_process(self, plugin_id: str, process, *, session_id: str):
        self.calls.append(("monitor_process", (plugin_id, process), {"session_id": session_id}))


@pytest.mark.asyncio
async def test_manager_runtime_methods_delegate_to_runtime_service() -> None:
    manager = object.__new__(PluginManager)
    manager._runtime_service = _RuntimeServiceDouble()
    process = object()

    start_port = await PluginManager.start_plugin(manager, "com.demo.app")
    stop_ok = await PluginManager.stop_plugin(manager, "com.demo.app")
    restart_port = await PluginManager.restart_plugin(manager, "com.demo.app")
    ready = await PluginManager._wait_for_ready(manager, "com.demo.app", process, timeout=12.5, session_id="s1")
    await PluginManager._monitor_process(manager, "com.demo.app", process, session_id="s2")

    assert start_port == 9527
    assert stop_ok is True
    assert restart_port == 9528
    assert ready is True
    assert manager._runtime_service.calls == [
        ("start_plugin", ("com.demo.app",), {}),
        ("stop_plugin", ("com.demo.app",), {}),
        ("restart_plugin", ("com.demo.app",), {}),
        ("wait_for_ready", ("com.demo.app", process, 12.5), {"session_id": "s1"}),
        ("monitor_process", ("com.demo.app", process), {"session_id": "s2"}),
    ]
