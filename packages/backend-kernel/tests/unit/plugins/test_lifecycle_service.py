from types import SimpleNamespace
import importlib
import sys
from types import ModuleType

import pytest


def _build_service(monkeypatch: pytest.MonkeyPatch):
    voice_module = ModuleType("app.voice")
    voice_module.get_tts_runtime_service = lambda: SimpleNamespace()
    monkeypatch.setitem(sys.modules, "app.voice", voice_module)
    module = importlib.import_module("app.plugins.lifecycle_service")
    return module.PluginLifecycleService(), module


@pytest.mark.asyncio
async def test_wait_preview_ready_returns_when_main_preview_running(monkeypatch: pytest.MonkeyPatch) -> None:
    service, module = _build_service(monkeypatch)
    manager = SimpleNamespace(
        get_plugin_preview_status=lambda _plugin_id: {
            "state": "running",
            "url": "http://127.0.0.1:5173/",
            "python_sidecar_port": 18081,
        }
    )
    monkeypatch.setattr(module, "get_plugin_manager", lambda: manager)

    ready = await service._wait_preview_ready("com.demo.app", timeout_seconds=1)

    assert ready is not None
    assert ready["url"] == "http://127.0.0.1:5173/"


@pytest.mark.asyncio
async def test_wait_preview_ready_ignores_sidecar_error_when_preview_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, module = _build_service(monkeypatch)
    manager = SimpleNamespace(
        get_plugin_preview_status=lambda _plugin_id: {
            "state": "running",
            "url": "http://127.0.0.1:5173/",
            "python_sidecar_port": 18081,
            "python_sidecar_state": "error",
            "python_sidecar_error_message": "sidecar failed",
        }
    )
    monkeypatch.setattr(module, "get_plugin_manager", lambda: manager)

    ready = await service._wait_preview_ready("com.demo.app", timeout_seconds=1)

    assert ready is not None
    assert ready["state"] == "running"
