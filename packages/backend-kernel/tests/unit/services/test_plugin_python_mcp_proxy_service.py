from __future__ import annotations

import pytest

from app.services import plugin_python_mcp_proxy_service as proxy_module
from app.services.plugin_mcp_proxy_service import PluginMcpProxyError
from app.services.plugin_python_mcp_proxy_service import (
    PluginPythonMcpProxyError,
    PluginPythonMcpProxyService,
)


class _ProxyStub:
    def __init__(self, *, payload: dict | None = None, error: Exception | None = None) -> None:
        self._payload = payload or {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        self._error = error

    async def forward_jsonrpc(self, plugin_id: str, payload: dict, endpoint: str):
        if self._error is not None:
            raise self._error
        assert endpoint == "python_sidecar"
        return self._payload


@pytest.mark.asyncio
async def test_forward_jsonrpc_success(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
    monkeypatch.setattr(proxy_module, "get_plugin_mcp_proxy_service", lambda: _ProxyStub(payload=expected))

    service = PluginPythonMcpProxyService()
    result = await service.forward_jsonrpc(
        plugin_id="com.demo.plugin",
        payload={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )

    assert result == expected


@pytest.mark.asyncio
async def test_forward_jsonrpc_raises_when_endpoint_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        proxy_module,
        "get_plugin_mcp_proxy_service",
        lambda: _ProxyStub(error=PluginMcpProxyError(code="plugin_python_unavailable", message="missing endpoint")),
    )

    service = PluginPythonMcpProxyService()
    with pytest.raises(PluginPythonMcpProxyError) as exc:
        await service.forward_jsonrpc(
            plugin_id="com.demo.plugin",
            payload={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )

    assert exc.value.code == "plugin_python_unavailable"
