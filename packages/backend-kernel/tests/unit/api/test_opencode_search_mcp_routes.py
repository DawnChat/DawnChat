import pytest

from app.api import opencode_search_mcp_routes as routes


@pytest.mark.asyncio
async def test_initialize_returns_search_server_info() -> None:
    body = routes.JsonRpcRequest(id=1, method="initialize")
    response = await routes.opencode_mcp_search(body)
    assert response["result"]["serverInfo"]["name"] == "dawnchat-opencode-search-mcp"


@pytest.mark.asyncio
async def test_tools_call_wraps_service_result(monkeypatch: pytest.MonkeyPatch) -> None:
    class _ServiceStub:
        def tool_definitions(self):
            return [{"name": "dawnchat.search.text", "description": "text", "inputSchema": {"type": "object"}}]

        async def execute(self, name: str, arguments: dict):
            return {"ok": True, "data": {"items": []}}

    monkeypatch.setattr(routes, "_hub", routes.OpenCodeMcpHub(routes.OpenCodeMcpHubConfig(
        mcp_name="search", server_name="dawnchat-opencode-search-mcp"
    ), service_factory=lambda: _ServiceStub()))

    body = routes.JsonRpcRequest(id=1, method="tools/call", params={"name": "dawnchat.search.text", "arguments": {}})
    response = await routes.opencode_mcp_search(body)
    assert response["result"]["isError"] is False
