import pytest

from app.api import opencode_mcp_routes as routes


class _UiServiceStub:
    def __init__(self, payload=None) -> None:
        self.payload = payload or {"ok": True, "data": {"elements": []}}

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
        return self.payload


@pytest.mark.asyncio
async def test_initialize_returns_server_info() -> None:
    body = routes.JsonRpcRequest(id=1, method="initialize")
    response = await routes.opencode_mcp_ui(body)
    assert response["result"]["serverInfo"]["name"] == "dawnchat-opencode-ui-mcp"


@pytest.mark.asyncio
async def test_tools_call_success_returns_tool_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "get_ui_tool_service", lambda: _UiServiceStub())
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
    body = routes.JsonRpcRequest(id=1, method="tools/call", params={"name": "dawnchat.ui.describe", "arguments": {}})
    response = await routes.opencode_mcp_ui(body)
    assert response["error"]["code"] == -32602
    assert response["error"]["data"]["error_code"] == "invalid_arguments"
