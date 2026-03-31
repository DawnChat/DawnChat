from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.services.plugin_mcp_proxy_service import PluginMcpProxyError, get_plugin_mcp_proxy_service


@dataclass(slots=True)
class PluginBackendMcpProxyError(Exception):
    code: str
    message: str


class PluginBackendMcpProxyService:
    async def forward_jsonrpc(self, plugin_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return await get_plugin_mcp_proxy_service().forward_jsonrpc(
                plugin_id=plugin_id,
                payload=payload,
                endpoint="backend",
            )
        except PluginMcpProxyError as err:
            raise PluginBackendMcpProxyError(code=err.code, message=err.message) from err


_plugin_backend_mcp_proxy_service: PluginBackendMcpProxyService | None = None


def get_plugin_backend_mcp_proxy_service() -> PluginBackendMcpProxyService:
    global _plugin_backend_mcp_proxy_service
    if _plugin_backend_mcp_proxy_service is None:
        _plugin_backend_mcp_proxy_service = PluginBackendMcpProxyService()
    return _plugin_backend_mcp_proxy_service
