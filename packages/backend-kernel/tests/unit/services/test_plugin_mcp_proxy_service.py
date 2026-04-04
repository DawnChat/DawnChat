from __future__ import annotations

import pytest

from app.services import plugin_id_resolver as resolver_module, plugin_mcp_proxy_service as proxy_module
from app.services.plugin_mcp_proxy_service import PluginMcpProxyError, PluginMcpProxyService


class _ManagerStub:
    def __init__(
        self,
        *,
        backend: dict | None,
        python_sidecar: dict | None,
        registered_ids: list[str] | None = None,
    ) -> None:
        self._backend = backend
        self._python_sidecar = python_sidecar
        self._registered_ids = set(registered_ids or [])
        self.last_backend_plugin_id = ""
        self.last_python_plugin_id = ""

    def get_plugin_snapshot(self, plugin_id: str):
        if plugin_id in self._registered_ids:
            return {"id": plugin_id}
        return None

    def resolve_mcp_endpoint(self, plugin_id: str):
        self.last_backend_plugin_id = plugin_id
        return self._backend

    def resolve_mcp_endpoints(self, plugin_id: str):
        self.last_python_plugin_id = plugin_id
        return {"backend": self._backend, "python_sidecar": self._python_sidecar}

    def list_plugins(self):
        return [{"id": plugin_id} for plugin_id in sorted(self._registered_ids)]


class _ResponseStub:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _ClientStub:
    def __init__(self, response=None, error: Exception | None = None):
        self._response = response or _ResponseStub(200, {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
        self._error = error

    async def post(self, url: str, json: dict):
        if self._error is not None:
            raise self._error
        return self._response


@pytest.mark.asyncio
async def test_forward_jsonrpc_backend_success(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _ManagerStub(
        backend={"port": 18000},
        python_sidecar=None,
        registered_ids=["com.demo.plugin"],
    )
    monkeypatch.setattr(proxy_module, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(proxy_module.httpx, "AsyncClient", lambda **kwargs: _ClientStub())
    service = PluginMcpProxyService()

    result = await service.forward_jsonrpc(
        plugin_id="com.demo.plugin",
        payload={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        endpoint="backend",
    )

    assert result["result"]["ok"] is True
    assert manager.last_backend_plugin_id == "com.demo.plugin"


@pytest.mark.asyncio
async def test_forward_jsonrpc_python_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _ManagerStub(
        backend={"port": 18000},
        python_sidecar=None,
        registered_ids=["com.demo.plugin"],
    )
    monkeypatch.setattr(
        proxy_module,
        "get_plugin_manager",
        lambda: manager,
    )
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(proxy_module.httpx, "AsyncClient", lambda **kwargs: _ClientStub())
    service = PluginMcpProxyService()

    with pytest.raises(PluginMcpProxyError) as exc:
        await service.forward_jsonrpc(
            plugin_id="com.demo.plugin",
            payload={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            endpoint="python_sidecar",
        )

    assert exc.value.code == "plugin_python_unavailable"


@pytest.mark.asyncio
async def test_forward_jsonrpc_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _ManagerStub(
        backend={"port": 18000},
        python_sidecar=None,
        registered_ids=["com.demo.plugin"],
    )
    monkeypatch.setattr(proxy_module, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(
        proxy_module.httpx,
        "AsyncClient",
        lambda **kwargs: _ClientStub(response=_ResponseStub(502, {"detail": "bad gateway"})),
    )
    service = PluginMcpProxyService()

    with pytest.raises(PluginMcpProxyError) as exc:
        await service.forward_jsonrpc(
            plugin_id="com.demo.plugin",
            payload={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            endpoint="backend",
        )

    assert exc.value.code == "plugin_backend_http_error"


@pytest.mark.asyncio
async def test_forward_jsonrpc_resolves_safe_name_to_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _ManagerStub(
        backend={"port": 18000},
        python_sidecar=None,
        registered_ids=["com.demo.plugin"],
    )
    monkeypatch.setattr(proxy_module, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(resolver_module, "get_plugin_manager", lambda: manager)
    monkeypatch.setattr(proxy_module.httpx, "AsyncClient", lambda **kwargs: _ClientStub())
    service = PluginMcpProxyService()

    result = await service.forward_jsonrpc(
        plugin_id="com_demo_plugin",
        payload={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        endpoint="backend",
    )

    assert result["result"]["ok"] is True
    assert manager.last_backend_plugin_id == "com.demo.plugin"
