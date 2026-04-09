import pytest

from app.api import opencode_mcp_routes as routes


class _UiServiceStub:
    def __init__(self, payload=None) -> None:
        self.payload = payload or {"ok": True, "data": {"elements": []}}
        self.calls: list[tuple[str, dict]] = []

    def tool_definitions(self):
        return [
            type(
                "Def",
                (),
                {
                    "name": "dawnchat.ui.describe",
                    "description": "describe",
                    "input_schema": {"type": "object"},
                },
            )()
        ]

    async def execute(self, name: str, arguments: dict):
        self.calls.append((name, dict(arguments)))
        return self.payload


class _ManagerStub:
    def __init__(self, startup_context=None, workspace_path: str = "") -> None:
        self.startup_context = dict(startup_context or {})
        self.workspace_path = workspace_path


@pytest.mark.asyncio
async def test_initialize_returns_server_info() -> None:
    body = routes.JsonRpcRequest(id=1, method="initialize")
    response = await routes.opencode_mcp_ui(body)
    assert response["result"]["serverInfo"]["name"] == "dawnchat-opencode-ui-mcp"


@pytest.mark.asyncio
async def test_tools_call_success_returns_tool_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "get_ui_tool_service", lambda: _UiServiceStub())
    monkeypatch.setattr(routes, "get_opencode_manager", lambda: _ManagerStub())
    body = routes.JsonRpcRequest(id=1, method="tools/call", params={"name": "dawnchat.ui.describe", "arguments": {}})
    response = await routes.opencode_mcp_ui(body)
    assert response["result"]["isError"] is False


@pytest.mark.asyncio
async def test_tools_call_failure_returns_jsonrpc_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes,
        "get_ui_tool_service",
        lambda: _UiServiceStub(payload={"ok": False, "error_code": "invalid_arguments", "message": "bad payload"}),
    )
    monkeypatch.setattr(routes, "get_opencode_manager", lambda: _ManagerStub())
    body = routes.JsonRpcRequest(id=1, method="tools/call", params={"name": "dawnchat.ui.describe", "arguments": {}})
    response = await routes.opencode_mcp_ui(body)
    assert response["error"]["code"] == -32602
    assert response["error"]["data"]["error_code"] == "invalid_arguments"


@pytest.mark.asyncio
async def test_tools_call_injects_active_plugin_workspace_plugin_id_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _UiServiceStub()
    monkeypatch.setattr(routes, "get_ui_tool_service", lambda: service)
    monkeypatch.setattr(
        routes,
        "get_opencode_manager",
        lambda: _ManagerStub(
            startup_context={
                "workspace_kind": "plugin-dev",
                "plugin_id": "com.demo.current",
            }
        ),
    )
    body = routes.JsonRpcRequest(
        id=1,
        method="tools/call",
        params={
            "name": "dawnchat.ui.describe",
            "arguments": {
                "scope": "visible",
            },
        },
    )

    response = await routes.opencode_mcp_ui(body)

    assert response["result"]["isError"] is False
    assert service.calls == [
        (
            "dawnchat.ui.describe",
            {
                "plugin_id": "com.demo.current",
                "scope": "visible",
            },
        )
    ]


@pytest.mark.asyncio
async def test_tools_call_returns_plugin_context_mismatch_with_workspace_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _UiServiceStub()
    monkeypatch.setattr(routes, "get_ui_tool_service", lambda: service)
    monkeypatch.setattr(
        routes,
        "get_opencode_manager",
        lambda: _ManagerStub(
            startup_context={
                "workspace_kind": "plugin-dev",
                "plugin_id": "com.demo.current",
            },
            workspace_path="/tmp/dawnchat/plugins/com.demo.current",
        ),
    )
    body = routes.JsonRpcRequest(
        id=1,
        method="tools/call",
        params={
            "name": "dawnchat.ui.describe",
            "arguments": {
                "plugin_id": "com.demo.stale",
                "scope": "visible",
            },
        },
    )

    response = await routes.opencode_mcp_ui(body)

    assert response["error"]["code"] == -32000
    assert response["error"]["data"]["error_code"] == "plugin_context_mismatch"
    assert response["error"]["data"]["details"] == {
        "requested_plugin_id": "com.demo.stale",
        "active_plugin_id": "com.demo.current",
        "active_workspace_path": "/tmp/dawnchat/plugins/com.demo.current",
        "workspace_kind": "plugin-dev",
    }
    assert service.calls == []
