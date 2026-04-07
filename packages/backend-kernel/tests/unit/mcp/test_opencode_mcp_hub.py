import pytest

from app.api.opencode_mcp_common import JsonRpcRequest
from app.mcp.opencode.hub import OpenCodeMcpHub, OpenCodeMcpHubConfig


class _ServiceStub:
    def __init__(self, payload=None) -> None:
        self.payload = payload or {"ok": True, "data": {"value": 1}}

    def tool_definitions(self):
        return [
            {
                "name": "dawnchat.search.text",
                "description": "search text",
                "inputSchema": {"type": "object"},
            }
        ]

    async def execute(self, name: str, arguments: dict):
        return self.payload


class _ProxyStub:
    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload or {"jsonrpc": "2.0", "id": "x1", "result": {"ok": True}}
        self.error = error

    async def forward_jsonrpc(self, payload: dict, context: dict):
        if self.error is not None:
            raise self.error
        return self.payload


@pytest.mark.asyncio
async def test_hub_initialize_returns_server_info() -> None:
    hub = OpenCodeMcpHub(
        OpenCodeMcpHubConfig(mcp_name="search", server_name="dawnchat-opencode-search-mcp"),
        service_factory=lambda: _ServiceStub(),
    )
    body = JsonRpcRequest(id=1, method="initialize")
    response = await hub.handle(body)
    assert response["result"]["serverInfo"]["name"] == "dawnchat-opencode-search-mcp"


@pytest.mark.asyncio
async def test_hub_tools_list_returns_normalized_tools() -> None:
    hub = OpenCodeMcpHub(
        OpenCodeMcpHubConfig(mcp_name="search", server_name="dawnchat-opencode-search-mcp"),
        service_factory=lambda: _ServiceStub(),
    )
    body = JsonRpcRequest(id=1, method="tools/list")
    response = await hub.handle(body)
    assert response["result"]["tools"][0]["name"] == "dawnchat.search.text"


@pytest.mark.asyncio
async def test_hub_tools_call_failure_returns_jsonrpc_error() -> None:
    hub = OpenCodeMcpHub(
        OpenCodeMcpHubConfig(mcp_name="search", server_name="dawnchat-opencode-search-mcp"),
        service_factory=lambda: _ServiceStub(
            payload={"ok": False, "error_code": "invalid_arguments", "message": "bad input"}
        ),
    )
    body = JsonRpcRequest(id=1, method="tools/call", params={"name": "dawnchat.search.text", "arguments": {}})
    response = await hub.handle(body)
    assert response["error"]["code"] == -32602
    assert response["error"]["data"]["error_code"] == "invalid_arguments"


@pytest.mark.asyncio
async def test_hub_proxy_mode_forwards_payload() -> None:
    expected = {"jsonrpc": "2.0", "id": "x1", "result": {"tools": [{"name": "demo.echo"}]}}
    hub = OpenCodeMcpHub(
        OpenCodeMcpHubConfig(
            mcp_name="plugin_backend",
            server_name="dawnchat-opencode-plugin-backend-mcp-proxy",
            mode="jsonrpc_proxy",
        ),
        proxy_factory=lambda: _ProxyStub(payload=expected),
    )
    body = JsonRpcRequest(id="x1", method="tools/list")
    response = await hub.handle(body, context={"plugin_id": "com.demo.plugin"})
    assert response == expected


@pytest.mark.asyncio
async def test_hub_proxy_mode_blocks_unsupported_method() -> None:
    hub = OpenCodeMcpHub(
        OpenCodeMcpHubConfig(
            mcp_name="plugin_backend",
            server_name="dawnchat-opencode-plugin-backend-mcp-proxy",
            mode="jsonrpc_proxy",
        ),
        proxy_factory=lambda: _ProxyStub(),
    )
    body = JsonRpcRequest(id=1, method="session/list")
    response = await hub.handle(body, context={"plugin_id": "com.demo.plugin"})
    assert response["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_hub_proxy_mode_maps_exception() -> None:
    hub = OpenCodeMcpHub(
        OpenCodeMcpHubConfig(
            mcp_name="plugin_backend",
            server_name="dawnchat-opencode-plugin-backend-mcp-proxy",
            mode="jsonrpc_proxy",
        ),
        proxy_factory=lambda: _ProxyStub(error=RuntimeError("boom")),
        proxy_error_mapper=lambda err: ("plugin_backend_unavailable", str(err)),
    )
    body = JsonRpcRequest(id=2, method="tools/call", params={"name": "demo.echo", "arguments": {}})
    response = await hub.handle(body, context={"plugin_id": "com.demo.plugin"})
    assert response["error"]["data"]["error_code"] == "plugin_backend_unavailable"
