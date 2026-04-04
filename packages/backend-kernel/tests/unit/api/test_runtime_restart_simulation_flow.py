from __future__ import annotations

import json

from fastapi import HTTPException
import pytest

from app.api import opencode_mcp_routes, plugins_routes
import app.plugin_ui_bridge.ui_tool_service as ui_tool_service_module
from app.plugin_ui_bridge.ui_tool_service import UiToolService
import app.services.plugin_id_resolver as plugin_id_resolver_module


class _ManagerStub:
    def get_plugin_snapshot(self, plugin_id: str):
        return {"id": plugin_id}


class _LifecycleProgressStub:
    def __init__(self) -> None:
        self._task_id = "task_restart_demo_1"
        self._poll_count = 0

    async def submit_restart_dev_session(self, plugin_id: str) -> str:
        return self._task_id

    def get_operation(self, task_id: str):
        if task_id != self._task_id:
            return None
        self._poll_count += 1
        if self._poll_count == 1:
            return {
                "task_id": task_id,
                "status": "running",
                "progress": {"message": "starting", "percent": 60},
            }
        return {
            "task_id": task_id,
            "status": "completed",
            "result": {"preview_url": "http://127.0.0.1:17961"},
        }


class _BridgeStub:
    async def dispatch(self, plugin_id: str, op, payload):
        raise AssertionError("runtime.restart should not dispatch bridge operations")


class _ArtifactStoreStub:
    def write_result(self, plugin_id: str, request_id: str, op, result):
        return {"data": result, "artifacts": []}


@pytest.mark.asyncio
async def test_runtime_restart_returns_task_then_polls_to_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    lifecycle = _LifecycleProgressStub()
    service = UiToolService(bridge_service=_BridgeStub(), artifact_store=_ArtifactStoreStub())
    monkeypatch.setattr(ui_tool_service_module, "get_plugin_manager", lambda: _ManagerStub())
    monkeypatch.setattr(plugin_id_resolver_module, "get_plugin_manager", lambda: _ManagerStub())
    monkeypatch.setattr(ui_tool_service_module, "get_plugin_lifecycle_service", lambda: lifecycle)
    monkeypatch.setattr(opencode_mcp_routes, "get_ui_tool_service", lambda: service)
    monkeypatch.setattr(plugins_routes, "get_plugin_lifecycle_service", lambda: lifecycle)

    body = opencode_mcp_routes.JsonRpcRequest(
        id=1,
        method="tools/call",
        params={
            "name": "dawnchat.ui.runtime.restart",
            "arguments": {"plugin_id": "com.demo.plugin"},
        },
    )
    call_result = await opencode_mcp_routes.opencode_mcp_ui(body)
    content_text = call_result["result"]["content"][0]["text"]
    payload = json.loads(content_text)
    task_id = payload["data"]["task_id"]

    first_poll = await plugins_routes.get_operation(task_id)
    second_poll = await plugins_routes.get_operation(task_id)

    assert first_poll["status"] == "success"
    assert first_poll["data"]["status"] == "running"
    assert second_poll["status"] == "success"
    assert second_poll["data"]["status"] == "completed"


@pytest.mark.asyncio
async def test_runtime_restart_poll_missing_task_raises_404(monkeypatch: pytest.MonkeyPatch) -> None:
    lifecycle = _LifecycleProgressStub()
    monkeypatch.setattr(plugins_routes, "get_plugin_lifecycle_service", lambda: lifecycle)

    with pytest.raises(HTTPException) as exc:
        await plugins_routes.get_operation("task_not_found")

    assert exc.value.status_code == 404
