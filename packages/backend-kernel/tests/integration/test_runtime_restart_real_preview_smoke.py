from __future__ import annotations

import asyncio
import json
import os
import time

import pytest

from app.api import opencode_mcp_routes, opencode_plugin_python_mcp_routes, plugins_routes
from app.plugins import get_plugin_manager


pytestmark = [pytest.mark.integration, pytest.mark.slow]


_ENABLE_ENV = "DAWNCHAT_RUN_REAL_PLUGIN_SMOKE"
_TARGET_PLUGIN_ID = "com.dawnchat.desktop-ai-assistant"


def _smoke_enabled() -> bool:
    return str(os.getenv(_ENABLE_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}


async def _poll_operation_until_completed(task_id: str, timeout_seconds: float = 150.0) -> dict:
    started = time.monotonic()
    while time.monotonic() - started <= timeout_seconds:
        payload = await plugins_routes.get_operation(task_id)
        data = payload.get("data") or {}
        status = str(data.get("status") or "")
        if status == "completed":
            return data
        if status in {"failed", "cancelled"}:
            raise AssertionError(f"lifecycle task ended with status={status}, payload={data}")
        await asyncio.sleep(1.0)
    raise AssertionError(f"timeout waiting lifecycle task completion: {task_id}")


def _decode_ui_tool_result(payload: dict) -> dict:
    result = payload.get("result") or {}
    content = result.get("content") or []
    if not isinstance(content, list) or not content:
        return {}
    text = str(content[0].get("text") or "{}")
    return json.loads(text)


async def _get_runtime_info() -> dict:
    runtime_rpc = opencode_mcp_routes.JsonRpcRequest(
        id="smoke-runtime-info",
        method="tools/call",
        params={
            "name": "dawnchat.ui.runtime.info",
            "arguments": {"plugin_id": _TARGET_PLUGIN_ID},
        },
    )
    runtime_result = await opencode_mcp_routes.opencode_mcp_ui(runtime_rpc)
    runtime_payload = _decode_ui_tool_result(runtime_result)
    data = runtime_payload.get("data") or {}
    assert isinstance(data, dict)
    return data


async def _assert_python_sidecar_ready() -> int:
    runtime_info = await _get_runtime_info()
    sidecar = runtime_info.get("python_sidecar") or {}
    endpoint = sidecar.get("endpoint") or {}
    assert str(sidecar.get("state") or "") == "running"
    port = int(endpoint.get("port") or 0)
    assert port > 0
    return port


async def _assert_python_mcp_proxy_works() -> None:
    tools_list_request = opencode_plugin_python_mcp_routes.JsonRpcRequest(id="smoke-python-list", method="tools/list")
    tools_list_result = await opencode_plugin_python_mcp_routes.opencode_plugin_python_mcp(
        _TARGET_PLUGIN_ID,
        tools_list_request,
    )
    tools = ((tools_list_result.get("result") or {}).get("tools") or [])
    tool_names = {str(tool.get("name") or "") for tool in tools if isinstance(tool, dict)}
    assert "assistant.python.echo" in tool_names

    call_request = opencode_plugin_python_mcp_routes.JsonRpcRequest(
        id="smoke-python-call",
        method="tools/call",
        params={"name": "assistant.python.echo", "arguments": {"message": "smoke"}},
    )
    call_result = await opencode_plugin_python_mcp_routes.opencode_plugin_python_mcp(_TARGET_PLUGIN_ID, call_request)
    content = ((call_result.get("result") or {}).get("content") or [{}])
    text = str(content[0].get("text") or "{}")
    payload = json.loads(text)
    data = payload.get("data") or {}
    assert data.get("service") == "python-sidecar"
    assert data.get("message") == "smoke"


@pytest.mark.asyncio
async def test_runtime_restart_real_preview_smoke() -> None:
    if not _smoke_enabled():
        pytest.skip(f"set {_ENABLE_ENV}=1 to run real preview smoke")

    manager = get_plugin_manager()
    ready = await manager.ensure_initialized()
    if not ready:
        pytest.skip("plugin manager initialization failed in current environment")
    plugin = manager.get_plugin_snapshot(_TARGET_PLUGIN_ID)
    if not plugin:
        pytest.skip(f"target plugin not found: {_TARGET_PLUGIN_ID}")

    try:
        start_task = await plugins_routes.start_dev_session_operation(
            plugins_routes.StartDevSessionOperationRequest(plugin_id=_TARGET_PLUGIN_ID)
        )
        start_task_id = str(start_task.get("task_id") or "")
        assert start_task_id
        await _poll_operation_until_completed(start_task_id)
        await _assert_python_sidecar_ready()
        await _assert_python_mcp_proxy_works()

        restart_rpc = opencode_mcp_routes.JsonRpcRequest(
            id="smoke-restart-1",
            method="tools/call",
            params={
                "name": "dawnchat.ui.runtime.restart",
                "arguments": {"plugin_id": _TARGET_PLUGIN_ID},
            },
        )
        restart_result = await opencode_mcp_routes.opencode_mcp_ui(restart_rpc)
        content_text = str((restart_result.get("result") or {}).get("content", [{}])[0].get("text") or "{}")
        restart_payload = json.loads(content_text)
        restart_task_id = str((restart_payload.get("data") or {}).get("task_id") or "")
        assert restart_task_id

        final = await _poll_operation_until_completed(restart_task_id)
        result_payload = final.get("result") or {}
        assert str(result_payload.get("preview_url") or "").startswith("http")
        await _assert_python_sidecar_ready()
        await _assert_python_mcp_proxy_works()
    finally:
        await manager.stop_plugin_preview(_TARGET_PLUGIN_ID)
