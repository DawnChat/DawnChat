import importlib
import asyncio
import sys
from types import ModuleType, SimpleNamespace

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


@pytest.mark.asyncio
async def test_create_dev_session_marks_main_assistant_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    service, module = _build_service(monkeypatch)
    captured: dict[str, object] = {}

    class _TaskManager:
        async def update_progress(self, *_args, **_kwargs) -> None:
            return

        async def submit(self, **kwargs) -> str:
            tid = kwargs.get("task_id")
            assert tid is not None
            assert tid in service._operations
            loop = asyncio.get_running_loop()
            loop.call_soon(lambda: asyncio.create_task(kwargs["executor_func"]()))
            return str(tid)

    async def _ensure_template_cached(*_args, **_kwargs) -> None:
        return

    async def _scaffold_plugin_from_template(**kwargs):
        captured.update(kwargs)
        return {"plugin_id": "com.demo.user.u1.dawnchat-ai-assistant"}

    async def _prepare_plugin_runtime(*_args, **_kwargs) -> None:
        return

    async def _start_plugin_preview(*_args, **_kwargs) -> str:
        return "http://127.0.0.1:17961"

    manager = SimpleNamespace(
        ensure_template_cached=_ensure_template_cached,
        scaffold_plugin_from_template=_scaffold_plugin_from_template,
        prepare_plugin_runtime=_prepare_plugin_runtime,
        start_plugin_preview=_start_plugin_preview,
        get_plugin_preview_status=lambda _plugin_id: {
            "state": "running",
            "url": "http://127.0.0.1:17961",
        },
    )
    monkeypatch.setattr(module, "get_task_manager", lambda: _TaskManager())
    monkeypatch.setattr(module, "get_plugin_manager", lambda: manager)

    task_id = await service.submit_create_dev_session(
        {
            "template_id": "com.dawnchat.desktop-ai-assistant",
            "app_type": "desktop",
            "name": "Main Assistant",
            "plugin_id": "com.demo.user.u1.dawnchat-ai-assistant",
            "description": "",
            "owner_email": "demo@example.com",
            "owner_user_id": "u1",
            "is_main_assistant": True,
        }
    )
    await asyncio.sleep(0.01)

    assert len(task_id) == 8
    assert task_id in service._operations
    assert captured["source_type"] == "official_user_main_assistant"
    assert captured["is_main_assistant"] is True
