import pytest

from app.api import opencode_plugin_python_mcp_routes as routes
from app.services.plugin_python_mcp_proxy_service import PluginPythonMcpProxyError


class _ProxyServiceStub:
    def __init__(self, payload=None, error: PluginPythonMcpProxyError | None = None) -> None:
        self.payload = payload or {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        self.error = error

    async def forward_jsonrpc(self, plugin_id: str, payload: dict):
        if self.error is not None:
            raise self.error
        return self.payload


@pytest.mark.asyncio
async def test_initialize_returns_local_server_info() -> None:
    body = routes.JsonRpcRequest(id=1, method="initialize")
    response = await routes.opencode_plugin_python_mcp("com.demo.plugin", body)

    assert response["result"]["serverInfo"]["name"] == "dawnchat-opencode-plugin-python-mcp-proxy"


@pytest.mark.asyncio
async def test_tools_list_forwards_to_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = {"jsonrpc": "2.0", "id": "x1", "result": {"tools": [{"name": "tutor.python.echo"}]}}
    monkeypatch.setattr(routes, "get_plugin_python_mcp_proxy_service", lambda: _ProxyServiceStub(payload=expected))
    body = routes.JsonRpcRequest(id="x1", method="tools/list")

    response = await routes.opencode_plugin_python_mcp("com.demo.plugin", body)

    assert response == expected


@pytest.mark.asyncio
async def test_tools_call_returns_error_when_proxy_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes,
        "get_plugin_python_mcp_proxy_service",
        lambda: _ProxyServiceStub(
            error=PluginPythonMcpProxyError(code="plugin_python_unavailable", message="missing endpoint")
        ),
    )
    body = routes.JsonRpcRequest(id=2, method="tools/call", params={"name": "tutor.python.echo", "arguments": {}})

    response = await routes.opencode_plugin_python_mcp("com.demo.plugin", body)

    assert response["error"]["code"] == -32000
    assert response["error"]["message"] == "missing endpoint"
    assert response["error"]["data"]["error_code"] == "plugin_python_unavailable"
