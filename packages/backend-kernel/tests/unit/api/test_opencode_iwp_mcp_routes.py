import pytest

from app.api import opencode_iwp_mcp_routes as routes


class _IwpServiceStub:
    def __init__(self, payload=None) -> None:
        self.payload = payload or {"ok": True, "data": {"status": "done"}}

    def tool_definitions(self):
        return [{"name": "dawnchat.iwp.build", "description": "build", "inputSchema": {"type": "object"}}]

    async def execute(self, name: str, arguments: dict):
        return self.payload


@pytest.mark.asyncio
async def test_initialize_returns_server_info() -> None:
    body = routes.JsonRpcRequest(id=1, method="initialize")
    response = await routes.opencode_mcp_iwp(body)
    assert response["result"]["serverInfo"]["name"] == "dawnchat-opencode-iwp-mcp"


@pytest.mark.asyncio
async def test_tools_call_success_returns_tool_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "get_iwp_mcp_service", lambda: _IwpServiceStub())
    body = routes.JsonRpcRequest(id=1, method="tools/call", params={"name": "dawnchat.iwp.build", "arguments": {}})
    response = await routes.opencode_mcp_iwp(body)
    assert response["result"]["isError"] is False


@pytest.mark.asyncio
async def test_tools_call_failure_returns_jsonrpc_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes,
        "get_iwp_mcp_service",
        lambda: _IwpServiceStub(payload={"ok": False, "error_code": "tool_failed", "message": "failed"}),
    )
    body = routes.JsonRpcRequest(id=1, method="tools/call", params={"name": "dawnchat.iwp.build", "arguments": {}})
    response = await routes.opencode_mcp_iwp(body)
    assert response["error"]["code"] == -32000
    assert response["error"]["data"]["error_code"] == "tool_failed"
